# GitHub Copilot Instructions — Hybrid Data Lineage Engine

## Project snapshot

Column-level data lineage for COBOL / JCL / PL-SQL estates.

| Layer | Technology | Entry point |
|---|---|---|
| Parsing | Python, hand-written regex state machines | `parsers/orchestrator.py` |
| AI resolution | LangGraph + `AIProvider` ABC (NVIDIA or Bedrock) | `ai_engine/lineage_graph.py` |
| Persistence | Neo4j 5 (idempotent MERGE) | `graph/writer.py`, `graph/queries.py` |
| API | FastAPI | `api/main.py` |
| UI | React 18 + React Flow + Dagre | `frontend/src/App.jsx` |
| Tests | pytest, no DB / AI / network | `tests/` |
| Package manager | `uv` (Python), `npm` (frontend) | `pyproject.toml`, `frontend/package.json` |

---

## Non-negotiable invariants — never break these

### 1. Three-channel contract: parsers never guess

Every data-movement-shaped construct must land in exactly one channel:

| Channel | Type | Provenance | Status |
|---|---|---|---|
| Fully mapped | `EntityNode` / `LineageEdge` | `DETERMINISTIC` | `CONFIRMED` |
| Runtime-dependent | `DynamicConstruct` → AI resolver | `AI_INFERRED` | `PROVISIONAL` |
| Detected but unsupported | `UnparsedStatement` | — | coverage log |

- **Never silently drop** a data-movement construct — that creates invisible false negatives.
- **Never guess** a mapping the parser cannot prove — that creates false positives.
- Adding support for a new construct means routing it to channel 1 and removing its `UnparsedStatement` detector entry, **not** suppressing the detector.

### 2. Column reference format

```
ENTITY_ID|COLUMN_NAME          # pipe separator, not dot
FILE:PROD.CUSTOMER.DAILY|*     # |* = record-level (whole row, no positional guessing)
TABLE:CRISK.CUST_ACCOUNT_MASTER|BOOK_ID
```

z/OS dataset names contain dots, so pipe is the separator throughout — in Python dataclasses, Neo4j properties, React Flow handle ids, and Neo4j `Column.id`. If you change this format, you must change **all four** simultaneously.

### 3. Entity id format

```python
f"{NodeKind.TABLE.value}:{'SCHEMA.TABLE_NAME'.upper()}"   # → "TABLE:SCHEMA.TABLE_NAME"
f"{NodeKind.FILE.value}:{'DSN'.upper()}"                  # → "FILE:DSN"
f"{NodeKind.PROGRAM.value}:{'PROGNAME'.upper()}"          # → "PROGRAM:PROGNAME"
```

Always uppercase. Always `Kind:NAME` with the NodeKind enum value prefix.

### 4. `LineageEdge.id` includes `transformation`

Two edges between the same source and target nodes with different transformations (e.g. one INSERT and one DELETE) must remain distinct edges. The `id` property hashes `(source_id, target_id, edge_type, program, transformation)`. The Neo4j writer MERGEs on `edge_id`, so changing the hash inputs will create duplicate edges on re-ingest.

### 5. Writer never deletes

`Neo4jWriter` only MERGEs — it never removes nodes, columns, or edges. After renaming or removing a parser construct, run `uv run python main.py ingest --wipe` or stale data will linger in the graph and the UI.

### 6. Column handle ids must match on both sides

React Flow column handles in `TableNode.jsx` use `${nodeId}|${colName}`. Neo4j `Column.id` is `${owner_id}|${col_name.upper()}`. `queries.py:_column_edges()` sets `sourceHandle` and `targetHandle` to these ids. If you change the format in any one place, change all three.

### 7. Do not remove `EdgeResolver`

`ai_engine/resolver.py::EdgeResolver` is actively imported by `tests/test_complex_lineage.py`. The production pipeline uses `LineageGraphRunner` (`lineage_graph.py`), but `EdgeResolver` is the reference implementation and test harness. Removing it breaks the test suite.

---

## Python conventions

### Imports and module boundaries

```python
# parsers/base.py defines all shared data types — import from here, never re-define
from parsers.base import EntityNode, LineageEdge, ColumnMapping, DynamicConstruct, Provenance, EdgeStatus, EdgeType, NodeKind, ParseResult

# Never import a concrete AI provider directly — always go through the factory
from ai_engine import get_provider   # ✓
from ai_engine.bedrock_provider import BedrockProvider  # ✗
```

### Dataclass patterns

```python
# EntityNode / LineageEdge are plain dataclasses — id is a computed property
node = EntityNode(kind=NodeKind.TABLE, name="CRISK.CUST_ACCOUNT_MASTER")
node.id   # → "TABLE:CRISK.CUST_ACCOUNT_MASTER"

edge = LineageEdge(source_id="PROGRAM:CRDB2EXT", target_id="TABLE:CRISK.CUST_ACCOUNT_MASTER",
                   edge_type=EdgeType.READS_FROM, program="CRDB2EXT")
edge.id   # SHA1-based hash — do not store separately, always call .id
```

### ColumnMapping — qualified refs

```python
# Source columns must be fully qualified with the owner entity id
ColumnMapping(
    source_columns=["TABLE:CRISK.CUST_ACCOUNT_MASTER|BOOK_ID"],  # qualified
    target_column="FILE:PROD.EXTRACT|BOOK_ID",                   # qualified
    transformation="MOVE BOOK-ID TO OUT-BOOK-ID",                # exact COBOL/SQL snippet
)
# Bare unqualified refs like "BOOK_ID" will break the Neo4j writer's _col_ref() fallback
```

### AI metadata structure

Every `AI_INFERRED` edge must carry this dict on `LineageEdge.ai_metadata`:

```python
{
    "provider": provider.name,        # "bedrock" | "nvidia"
    "model": provider.model_id,
    "construct_id": construct.id,
    "construct_type": construct.construct_type,
    "source": f"{construct.path}:{construct.line}",
    "prompt_context": user_prompt[:1500],
    "self_confidence": 0.0–1.0,       # resolver's own score
    "judge_confidence": 0.0–1.0,      # evaluator's score (gates entry)
    "judge_rationale": "...",
}
```

---

## Parser extension guide

When adding support for a new COBOL/JCL/PL-SQL construct:

1. **If fully mappable**: emit `EntityNode`/`LineageEdge` with `provenance=Provenance.DETERMINISTIC`. Remove the corresponding `UnparsedStatement` detector entry (don't just suppress it).
2. **If runtime-dependent** (dynamic table name, symbolic value only known at job submission): emit `DynamicConstruct` with `snippet` + `context` (surrounding 20–40 lines). The LangGraph resolver will handle it.
3. **Never skip a data-movement-shaped construct entirely** — that's a false negative. `tests/test_coverage_telemetry.py` has zero-noise assertions that will catch it.

Parser structure — all three parsers follow the same contract:
```python
def parse(path: Path) -> ParseResult:
    ...
```
`ParserOrchestrator` calls `parse()` on each file and runs post-processing (DD cross-linking, nested CALL resolution, FD alias canonicalisation, entity⊇column reconciliation).

---

## AI resolver guide (`ai_engine/`)

### LangGraph state machine (`lineage_graph.py`)

The production resolver is a compiled `StateGraph`. Nodes and their responsibilities:

| Node | Responsibility |
|---|---|
| `resolve_node` | One LLM call per construct; deduplicates proposals |
| `fan_out_proposals` | `Send` per proposal (parallel branches; `operator.add` reducers merge outputs) |
| `evaluate_node` | Independent LLM-as-judge per proposal; fails closed |
| `column_retry_node` | **Reflexion**: accepted WRITES_TO with no column mappings → re-invoke LLM with `_COLUMN_SYSTEM` prompt |
| `emit_node` | Build `EntityNode` + `LineageEdge` with full audit trail |

Routing logic in `route_after_evaluate`:
- `confidence < threshold` → `"drop"` → END
- accepted + `WRITES_TO` + no column mappings → `"column_retry"`
- otherwise → `"emit"`

### Prompt constants (defined in `resolver.py`, imported by `lineage_graph.py`)

```python
from .resolver import _SYSTEM, _COLUMN_SYSTEM, _named
```

- `_SYSTEM` — main resolver prompt; expects `{"lineage": [...], "confidence_score", "reasoning"}`
- `_COLUMN_SYSTEM` — column-detail retry prompt; expects `{"column_mappings": [...], "reasoning"}`
- `_named(value)` — returns False for `None`, `""`, `"null"`, `"?"`, `"unknown"`, `"n/a"`, `"*"`

### Adding a new LLM provider

1. Subclass `AIProvider` in `ai_engine/base.py` — implement `embed`, `complete`, `complete_json`, `name`, `model_id`.
2. Register in `ai_engine/factory.py`.
3. No other files need changing.

---

## Neo4j writer rules

```python
# Column-level TRANSFORMS_TO stores these properties — always include all of them:
r.transformation = cm.transformation   # the COBOL/SQL expression
r.provenance     = edge.provenance.value
r.status         = edge.status.value
r.confidence     = edge.confidence
r.reasoning      = edge.reasoning
r.evidence       = edge.evidence       # source snippet (parent edge evidence propagated)
r.ai_metadata    = json.dumps(edge.ai_metadata) if edge.ai_metadata else None
```

`_col_ref(ref, fallback_owner)` in `writer.py`:
- If `ref` contains `|` → splits into `(col_id, owner_id, col_name)`.
- If bare name (no `|`) → uses `fallback_owner` as the owner. This is only a fallback — always emit qualified refs from parsers.

---

## API response shapes

### Entity-level edge (`_entity_neighbourhood`)
```json
{
  "id": "edge_id",
  "source": "PROGRAM:CRDB2EXT",
  "target": "TABLE:CRISK.CUST_ACCOUNT_MASTER",
  "data": {
    "edge_type": "READS_FROM",
    "program": "CRDB2EXT",
    "transformation": "DECLARE CURSOR ...",
    "provenance": "DETERMINISTIC",
    "status": "CONFIRMED",
    "confidence": 1.0,
    "evidence": null,
    "reasoning": null,
    "ai_metadata": {}
  }
}
```

### Column-level edge (`_column_edges`)
```json
{
  "id": "edge_id:SRC_COL>TGT_COL",
  "source": "TABLE:CRISK.CUST_ACCOUNT_MASTER",
  "target": "FILE:PROD.EXTRACT",
  "sourceHandle": "TABLE:CRISK.CUST_ACCOUNT_MASTER|BOOK_ID",
  "targetHandle": "FILE:PROD.EXTRACT|BOOK_ID",
  "data": {
    "edge_type": "TRANSFORMS_TO",
    "source_column": "BOOK_ID",
    "target_column": "BOOK_ID",
    "transformation": "MOVE BOOK-ID TO OUT-BOOK-ID",
    "provenance": "DETERMINISTIC",
    "status": "CONFIRMED",
    "confidence": 1.0,
    "reasoning": null,
    "evidence": null,
    "ai_metadata": {}
  }
}
```

---

## Frontend conventions (`frontend/src/`)

### Edge data contract
`LineageEdge.jsx` reads these fields from `data`:

| Field | Used for |
|---|---|
| `data.provenance` | Stroke color — `AI_INFERRED` → red dashed, else blue solid |
| `data.edge_type` | `EXECUTES` → yellow stroke |
| `data.transformation` | Tooltip + side panel code block |
| `data.evidence` | Side panel "Source Evidence" section (AI edges only) |
| `data.reasoning` | Tooltip + side panel AI reasoning |
| `data.confidence` | Badge `AI nn%` |
| `data.ai_metadata` | `{model, judge_rationale}` in tooltip / side panel |
| `data.source_column` / `data.target_column` | Column mapping display |
| `data.hot` / `data.dim` | Column path highlighting (set by `App.jsx`, not API) |

### Side panel (`TransformationPanel` in `App.jsx`)
- Opened by `onEdgeClick` on the ReactFlow component (not on the edge component itself).
- Closed by pane click (`onPaneClick`) or re-clicking the same edge.
- Language detection (`detectLang`): scores SQL patterns vs COBOL patterns against `data.transformation` text — returns `'sql'` | `'cobol'` | `'text'`.
- State: `selectedEdge` in `App` (snapshot at click time — `hot`/`dim` changes don't need to update it).

### Column path highlighting
- `focusCol` state = single column handle id (e.g. `"TABLE:CRISK.CUST_ACCOUNT_MASTER|BOOK_ID"`).
- `graphViews.columnPath(focusCol, view.edges)` BFS-walks `TRANSFORMS_TO` edges that have `sourceHandle`/`targetHandle`.
- Updates `edge.data.hot`/`dim` and `node.data.dimmed`/`focusCols` via `setEdges`/`setNodes` — **no re-layout**.

### Adding a new node type
1. Create component in `frontend/src/components/`.
2. Add to `nodeTypes` object in `App.jsx`.
3. Match the `isProcess()` predicate in `graphViews.js` if it's a process node.
4. Add entity-handle and optional column-handles (must use `${id}|${colName}` format).

### CSS theme tokens
All colors are CSS custom properties on `:root` / `[data-theme='dark']` in `styles.css`. Never hardcode colors in components — always use `var(--edge-det)`, `var(--edge-ai)`, `var(--entity-table-bg)`, etc.

---

## Testing guide

### Golden rules
- Tests in `tests/` must **never** require Neo4j, a live AI provider, or network access.
- `FakeProvider` in `test_complex_lineage.py` pops from a `list[dict]` — one pop per `complete_json` call. Use `provider.call_count` to assert exact LLM call counts.
- Parser tests use `ParserOrchestrator().parse_tree(SOURCE)` against real `mock-code/` files — these are the integration ground truth.

### What to test when extending parsers
- New mapped construct: assert the `EntityNode`/`LineageEdge` is present with correct `source_id`, `target_id`, `edge_type`, and at least one `ColumnMapping`.
- New telemetry entry: assert `result.unparsed` contains the `UnparsedStatement` with the correct `statement_type`.
- New dynamic construct: assert `result.dynamic_constructs` contains it and that **no** deterministic edges are emitted for it.
- Estate-wide counts: if you add/remove from the mock corpus, update the exact-count assertions (`test_exactly_two_flagged_constructs`, `test_cobol_move_telemetry`).

### What to test when extending the AI layer

```python
# Minimal FakeProvider setup for a resolver test:
provider = FakeProvider([
    {resolver_response},      # complete_json call 1: resolver
    {judge_response},         # complete_json call 2: evaluator
    # optional:
    {column_retry_response},  # complete_json call 3: column_retry_node (WRITES_TO + no cols)
])
resolver = EdgeResolver(provider, threshold=0.6)   # or LineageGraphRunner
_, edges = resolver.resolve_all([construct], known_entities=[])
assert provider.call_count == 2  # or 3 for retry path
```

---

## Common mistakes to avoid

| Mistake | Correct approach |
|---|---|
| Emitting `DynamicConstruct` for a fully static construct | Use channel 1 (mapped) |
| Using bare column name in `ColumnMapping.source_columns` | Always qualify: `"ENTITY_ID\|COL"` |
| Hardcoding a concrete AI provider in a call site | Use `factory.get_provider()` |
| Calling `writer.write()` after removing a node/edge in a parser | Add `--wipe` to the ingest call |
| Adding a new node type to ReactFlow without column handles | Add `Handle` per column with `id="${nodeId}\|${col}"` |
| Changing column-id format in one place only | Must update: `writer.py`, `queries.py`, `TableNode.jsx` |
| Removing `EdgeResolver` | It is used by the test suite — keep it |
| Putting any test logic that requires a running Neo4j or live LLM | Use `FakeProvider` or `tmp_path` fixtures |
| Asserting `node.columns` contains DB2 source-table columns | Source-table columns come from edge writer's HAS_COLUMN path, not `node.columns` |
