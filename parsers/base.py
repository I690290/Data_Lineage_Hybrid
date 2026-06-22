"""Shared data model for the deterministic parsing layer.

Every parser (COBOL / JCL / PL-SQL) emits the same three artefacts:

* ``EntityNode``      - a Table, File/Dataset, Program or Job node.
* ``LineageEdge``     - entity-level data movement (READS_FROM / WRITES_TO /
                        TRANSFORMS_TO) plus optional column-level mappings.
* ``DynamicConstruct``- a fragment the deterministic parser could NOT resolve
                        (dynamic SQL, JCL system symbolics, ...).  These are
                        handed to the AI edge-resolution layer.

Determinism contract: parsers never guess.  If a construct is not statically
resolvable it is flagged, never silently dropped or invented.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class NodeKind(str, Enum):
    TABLE = "Table"
    FILE = "File"          # flat file / z-OS dataset
    PROGRAM = "Program"    # COBOL program, PL/SQL procedure
    JOB = "Job"            # JCL job


class EdgeType(str, Enum):
    READS_FROM = "READS_FROM"
    WRITES_TO = "WRITES_TO"
    TRANSFORMS_TO = "TRANSFORMS_TO"   # column -> column
    EXECUTES = "EXECUTES"             # job -> program


class Provenance(str, Enum):
    DETERMINISTIC = "DETERMINISTIC"
    AI_INFERRED = "AI_INFERRED"


class EdgeStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    PROVISIONAL = "PROVISIONAL"   # AI-inferred, pending human review
    REJECTED = "REJECTED"


@dataclass
class ColumnMapping:
    """Column-level lineage: source column(s) -> target column."""
    source_columns: list[str]            # qualified "ENTITY.COLUMN"
    target_column: str                   # qualified "ENTITY.COLUMN"
    transformation: str = "direct"       # full logic as text (source->target)
    # ordered transformation steps, source -> target (every WS/host-var hop,
    # COMPUTE, STRING, TRIM, group move, ...). The frontend renders this as a
    # step-by-step chain; ``transformation`` is the same content joined.
    transform_steps: list[str] = field(default_factory=list)


@dataclass
class EntityNode:
    kind: NodeKind
    name: str                            # canonical upper-case name
    language: Optional[str] = None       # COBOL / JCL / PLSQL (programs)
    path: Optional[str] = None           # source file the node came from
    columns: list[str] = field(default_factory=list)
    attributes: dict = field(default_factory=dict)

    @property
    def id(self) -> str:
        return f"{self.kind.value}:{self.name}".upper()


@dataclass
class LineageEdge:
    source_id: str                       # EntityNode.id
    target_id: str                       # EntityNode.id
    edge_type: EdgeType
    program: Optional[str] = None        # program that causes the movement
    transformation: Optional[str] = None # entity-level logic summary
    column_mappings: list[ColumnMapping] = field(default_factory=list)
    provenance: Provenance = Provenance.DETERMINISTIC
    status: EdgeStatus = EdgeStatus.CONFIRMED
    confidence: float = 1.0
    evidence: Optional[str] = None       # source snippet / AI rationale
    reasoning: Optional[str] = None      # AI explanation (AI_INFERRED only)
    ai_metadata: dict = field(default_factory=dict)  # audit: model, prompt, judge

    @property
    def id(self) -> str:
        raw = (f"{self.source_id}|{self.edge_type.value}|{self.target_id}"
               f"|{self.program}|{self.transformation}")
        return hashlib.sha1(raw.encode()).hexdigest()[:16]


@dataclass
class DynamicConstruct:
    """A fragment the deterministic parser flagged as unresolvable."""
    program: str
    language: str                        # COBOL / JCL / PLSQL
    construct_type: str                  # e.g. DYNAMIC_SQL, JCL_SYMBOLIC
    snippet: str                         # the offending statement(s)
    context: str                         # surrounding code for the LLM
    path: str
    line: int

    @property
    def id(self) -> str:
        raw = f"{self.path}|{self.line}|{self.construct_type}"
        return hashlib.sha1(raw.encode()).hexdigest()[:16]


@dataclass
class UnparsedStatement:
    """Coverage telemetry: a data-movement-shaped statement the deterministic
    parser *detected* but could not map.

    This is the third output channel, distinct from the other two:
      * mapped statements        -> nodes/edges          (fails correct)
      * dynamic constructs       -> DynamicConstruct     (fails loud, AI path)
      * unsupported static code  -> UnparsedStatement    (fails loud, human path)

    Without this channel, unsupported constructs would be silent false
    negatives - lineage gaps with no signal that anything is missing.
    """
    program: str
    language: str                # COBOL / JCL / PLSQL
    statement_type: str          # e.g. COBOL_MOVE, EXEC_SQL_UPDATE, JCL_PROC
    snippet: str
    path: str
    line: int
    reason: str                  # why it could not be mapped


@dataclass
class ParseResult:
    path: str
    language: str
    nodes: list[EntityNode] = field(default_factory=list)
    edges: list[LineageEdge] = field(default_factory=list)
    dynamic_constructs: list[DynamicConstruct] = field(default_factory=list)
    unparsed: list[UnparsedStatement] = field(default_factory=list)

    def merge(self, other: "ParseResult") -> None:
        self.nodes.extend(other.nodes)
        self.edges.extend(other.edges)
        self.dynamic_constructs.extend(other.dynamic_constructs)
        self.unparsed.extend(other.unparsed)
