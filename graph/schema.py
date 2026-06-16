"""Neo4j schema.

Node labels:    Table | File | Program | Job | Column
Relationships:  READS_FROM | WRITES_TO | EXECUTES   (entity level)
                HAS_COLUMN                          (entity -> column)
                TRANSFORMS_TO                       (column -> column)

Every lineage relationship carries:
    provenance  DETERMINISTIC | AI_INFERRED
    status      CONFIRMED | PROVISIONAL | REJECTED
    confidence  0.0 - 1.0
    transformation / evidence  (logic captured as text)

Column references use the unambiguous form ``<ENTITY_ID>|<COLUMN>`` because
z/OS dataset names themselves contain dots.
"""

CONSTRAINTS = [
    "CREATE CONSTRAINT table_id IF NOT EXISTS FOR (n:Table) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT file_id IF NOT EXISTS FOR (n:File) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT program_id IF NOT EXISTS FOR (n:Program) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT job_id IF NOT EXISTS FOR (n:Job) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT column_id IF NOT EXISTS FOR (n:Column) REQUIRE n.id IS UNIQUE",
    "CREATE INDEX entity_name IF NOT EXISTS FOR (n:Table) ON (n.name)",
]

ENTITY_LABELS = {"Table", "File", "Program", "Job"}
LINEAGE_RELS = {"READS_FROM", "WRITES_TO", "EXECUTES"}
