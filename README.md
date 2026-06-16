# Hybrid Data Lineage Engine

Column-level data lineage for legacy **COBOL / JCL / PL-SQL** estates, built on the
**Hybrid Approach**: a deterministic parsing core is the source of truth; a LangGraph
agentic layer resolves *only* the constructs static analysis cannot
(dynamic SQL, JCL system symbolics) — and everything it produces enters the
graph as **PROVISIONAL**, gated by an LLM-as-judge evaluation pass and queued
for human review.

```
mock-code/ (COBOL/JCL/SQL)
   │
   ▼
┌─────────────────────────┐   flagged constructs   ┌──────────────────────────────┐
│ Deterministic parsers   │ ──────────────────────▶│ AI agentic resolver          │
│  parsers/  (COBOL, JCL, │                        │  ai_engine/lineage_graph.py  │
│  sqlparse-based PL/SQL) │                        │                              │
│  provenance=DETERMINISTIC                        │  React + Reflexion (LangGraph│
│  status=CONFIRMED       │                        │  state machine):             │
└───────────┬─────────────┘                        │  resolve → fan-out →         │
            │                                      │  evaluate → [drop |          │
            │                                      │  column_retry → emit]        │
            │                                      │  provenance=AI_INFERRED      │
            │                                      │  status=PROVISIONAL          │
            │                                      └────────────┬─────────────────┘
            ▼                                                   │
       ┌─────────────────────── Neo4j (graph/) ◀────────────────┘
       │   Table | File | Program | Job | Column
       │   READS_FROM | WRITES_TO | EXECUTES | HAS_COLUMN | TRANSFORMS_TO
       ▼
   FastAPI (api/)  ──▶  React + React Flow (frontend/)
   /lineage/{id}        TableNode / ProcessNode, column drill-down,
                        transformation side panel (click any edge to see
                        full SQL/COBOL code with Copy button),
                        solid-blue deterministic vs dashed-red AI edges
```

## Project layout

```
COBOL_Data_Lineage/
├── mock-code/              # MI4014 Credit Risk Behaviour Scoring estate
│   ├── COBOL/              #   CRDB2EXT (DB2 cursor → flat file),
│   │   │                   #   CRTXNEXT (file-driven DB2 cursor → flat file),
│   │   │                   #   CRXMLGEN (merged file → XML)
│   │   └── copybooks/      #   CRCUSTAC / CRTRANSR / CRXMLTAG
│   ├── JCL/                #   CRJBHSCR: 6-step pipeline incl. DFSORT
│   │                       #   JOINKEYS merge + FTP with &DATE symbolic
│   ├── SQL/                #   Oracle external table over the XML,
│   │                       #   PRC_MI4014_STAGE_LOAD stored procedure,
│   │                       #   3 analytical views
│   ├── data/               #   sample .dat / .xml payloads (not parsed)
│   └── production_complex/ # MI5021 Credit Risk Counterparty estate
│       ├── COBOL/          #   CRRSKMST (nested CALL→CRRSKSUB), copybooks
│       └── JCL/            #   CRJMI521 (IKJEFT01/DSNTIAUL unload)
├── parsers/                # deterministic core
│   ├── base.py             #   shared model: nodes, edges, DynamicConstruct flags
│   ├── cobol_parser.py     #   fixed-format normaliser, COPY expansion, FD fields,
│   │                       #   MOVE/COMPUTE/STRING transform chains, EXEC SQL
│   ├── jcl_parser.py       #   continuation-aware, SET symbol substitution, DD→DSN
│   ├── plsql_parser.py     #   sqlparse-based; INSERT-SELECT / MERGE column mapping
│   ├── orchestrator.py     #   tree walk + JCL↔COBOL DD cross-linking
│   ├── sort_resolver.py    #   DFSORT FIELDS= / JOINKEYS column mapping
│   └── sql_utils.py        #   shared SQL helpers (alias map, source columns)
├── ai_engine/              # AI agentic layer (Strategy/Adapter pattern)
│   ├── base.py             #   AIProvider ABC: embed / complete / complete_json
│   ├── nvidia_provider.py  #   NVIDIA NIM (OpenAI-compatible API)
│   ├── bedrock_provider.py #   Amazon Bedrock (Converse + Titan embeddings)
│   ├── factory.py          #   config.yaml → provider selection
│   ├── resolver.py         #   EdgeResolver (reference impl + shared prompts/helpers)
│   ├── evaluator.py        #   independent LLM-as-judge confidence gate
│   └── lineage_graph.py    #   LineageGraphRunner — React+Reflexion LangGraph state
│                           #   machine (production resolver used by main.py)
├── graph/                  # Neo4j layer
│   ├── schema.py           #   constraints + label/relationship definitions
│   ├── writer.py           #   idempotent MERGE upserts (entity + column level)
│   └── queries.py          #   lineage traversals shaped for React Flow
├── api/main.py             # FastAPI: /entities, /lineage/{id}, /provisional, review
├── frontend/               # React + React Flow + dagre Lineage UI
│   └── src/
│       ├── App.jsx         #   main shell, side panel state, edge-click handler
│       ├── components/
│       │   ├── TableNode.jsx    # entity node with per-column handles
│       │   ├── ProcessNode.jsx  # program/job node
│       │   └── LineageEdge.jsx  # provenance-styled edge + hover tooltip
│       ├── graphViews.js   #   deriveDataFlow / deriveProcessFlow / columnPath
│       ├── layout.js       #   Dagre auto-layout
│       ├── api.js          #   fetch wrappers
│       └── styles.css      #   theme tokens, node/edge/panel CSS
├── tests/
│   ├── test_parsers.py          # deterministic parser correctness
│   ├── test_complex_lineage.py  # MI5021 end-to-end + AI engine contract
│   └── test_coverage_telemetry.py  # three-channel invariant per detector family
├── main.py                 # CLI: ingest | export
├── config.py               # config loader (config.yaml + .env)
├── config.yaml             # provider toggle, confidence threshold, Neo4j, source dir
├── docker-compose.yml      # Neo4j 5 container
├── setup.sh                # one-shot environment setup
└── pyproject.toml          # uv-managed dependencies (incl. langgraph)
```

## Quick start

### 0. Prerequisites
- [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- Node.js ≥ 18 (frontend)
- Docker (Neo4j) — or any Neo4j 5 reachable at `bolt://localhost:7687`

### 1. Setup
```bash
./setup.sh          # uv sync + npm install + .env + docker compose up neo4j
```

### 2. Configure credentials (`.env`)
Pick a provider in `config.yaml` (`ai.provider: bedrock | nvidia`) and set the
matching secrets in `.env`:

| Provider | `.env` keys |
|---|---|
| Bedrock | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION` |
| NVIDIA  | `NVIDIA_API_KEY` (from <https://build.nvidia.com>) |

`NEO4J_PASSWORD` defaults to `neo4j_lineage` (must match the container).
You can also override per-run: `AI_PROVIDER=nvidia uv run python main.py ingest`.

### 3. Start Neo4j (if setup.sh didn't)
```bash
docker compose up -d neo4j
# browser: http://localhost:7474   bolt: 7687   auth: neo4j / $NEO4J_PASSWORD
```

### 4. Run the ingestion pipeline
```bash
uv run python main.py ingest            # deterministic parse + AI resolution → Neo4j
uv run python main.py ingest --no-ai    # deterministic-only (constructs stay flagged)
uv run python main.py ingest --wipe     # clear the graph first
uv run python main.py export -o lineage.json   # no Neo4j needed - JSON dump
```

### 5. Serve the API and UI
```bash
uv run uvicorn api.main:app --reload    # http://localhost:8000/docs
cd frontend && npm run dev              # http://localhost:5173
```

## API

| Endpoint | Description |
|---|---|
| `GET /entities` | catalogue of Tables / Files / Programs / Jobs |
| `GET /lineage/{entity_id}?depth=3&level=table\|column` | graph neighbourhood; `level=column` adds per-column `TRANSFORMS_TO` edges with `sourceHandle`/`targetHandle` for React Flow |
| `GET /provisional` | AI-inferred edges awaiting human review |
| `POST /provisional/{edge_id}/review` `{"approve": true}` | confirm or reject a provisional edge |

Entity ids look like `TABLE:CUSTOMER_MASTER`, `FILE:PROD.CUSTOMER.DAILY.EXTRACT`,
`PROGRAM:CUSTLOAD`.

## Design notes

**Determinism first.** Parsers never guess. Anything not statically resolvable
becomes a `DynamicConstruct` flag (with the surrounding code as context). The
MI4014 estate is captured end-to-end deterministically —
`DB2 CRISK.* → CRDB2EXT/CRTXNEXT → DFSORT JOINKEYS → CRXMLGEN → XML →
Oracle external table → PRC_MI4014_STAGE_LOAD → staging → views` — with column
lineage at every hop, and exactly one flagged gap: the FTP step's
`put ... MI4014_..._&DATE..xml`, whose date-templated remote name only the AI
layer can bridge.

**Coverage telemetry — no silent gaps.** The parsers have three output
channels, and *nothing* data-movement-shaped falls between them:

| Channel | Trigger | Fate |
|---|---|---|
| nodes/edges | construct fully mapped | CONFIRMED lineage |
| `DynamicConstruct` | construct is runtime-dependent (dynamic SQL, symbolics) | AI edge-resolution → PROVISIONAL |
| `UnparsedStatement` | construct is static but **unsupported** (COBOL `CALL`/`UNSTRING`/reference modification, unhandled `EXEC SQL` verbs, JCL `EXEC <proc>`/referbacks/GDG, SQL CTE inserts, …) | logged as `COVERAGE` warnings + exported in `lineage.json` |

Run `uv run python main.py export` against any estate and the engine reports
its own parsing blind spots per file/line.

**AI agentic resolver — React + Reflexion (LangGraph).** The production resolver
(`ai_engine/lineage_graph.py`) is a LangGraph state machine with four nodes:

```
resolve_node  →  fan-out (one branch per proposal)
                    └─► evaluate_node  →  DROP → END
                                      →  EMIT → emit_node → END
                                      →  REFLEXION → column_retry_node → emit_node → END
```

- **React**: `resolve_node` makes one LLM call per construct, produces all proposals.
- **Reflect**: `evaluate_node` (independent LLM-as-judge) scores each proposal separately.
- **Reflexion**: when an accepted `WRITES_TO` edge has no column mappings, `column_retry_node`
  observes the gap, feeds the accepted edge back as context, and re-invokes the LLM with a
  focused column-level prompt before emitting.

`EdgeResolver` (`resolver.py`) implements the same pipeline imperatively and is kept as the
reference implementation used by the test suite. Both share the same prompt constants and
helper functions.

**AI is quarantined.** All AI-proposed edges carry
`provenance=AI_INFERRED, status=PROVISIONAL, confidence, evidence, ai_metadata`
(provider, model, judge confidence, judge rationale) and render as dashed-red edges in
the UI until a human approves them via `POST /provisional/{edge_id}/review`.

**Transformation side panel.** Clicking any edge in the UI opens a right-side panel
showing the full transformation code (SQL or COBOL, auto-detected) with a Copy button.
AI edges additionally show confidence %, reasoning, and model metadata. The panel uses
the same `transformation` and `evidence` fields stored on both entity-level and
column-level relationships in Neo4j.

**Column references** use `<ENTITY_ID>|<COLUMN>` (a `|` separator) because
z/OS dataset names themselves contain dots.

**Swapping providers** is a one-line change (`config.yaml → ai.provider`) —
both adapters implement the same `AIProvider` strategy interface
(`embed`, `complete`, `complete_json`). The LangGraph resolver is provider-agnostic
and deploys to AWS Lambda / ECS / Step Functions as plain Python.

**Parser extensibility:** the COBOL/JCL parsers are hand-written
grammar-driven parsers behind the same `parse(path) -> ParseResult` contract;
a full ANTLR COBOL85 grammar can replace the implementation without touching
the rest of the pipeline.
