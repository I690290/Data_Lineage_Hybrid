/**
 * View derivations over the raw lineage graph returned by the API.
 *
 * The backend graph mixes Data Entities (Table / File) and Process steps
 * (Program / Job).  Enterprise lineage UIs separate the two concerns:
 *
 *  - "Data Lineage"    : entity-to-entity. Process hops (entity -READS_FROM->
 *    process -WRITES_TO-> entity) are collapsed into a single synthetic
 *    DATA_FLOW edge that remembers which process moved the data (`via`).
 *  - "Process Lineage" : process-to-process. Shared datasets are collapsed
 *    into HANDOFF edges (`via` = the dataset), EXECUTES edges are kept.
 */

const PROCESS_KINDS = new Set(['Program', 'Job']);

export const isProcess = (node) => PROCESS_KINDS.has(node.kind);

/** Table | View | External table | File - drives badges and styling. */
export function entityType(node) {
  if (node.kind === 'File') return 'file';
  const objectType = node.attributes?.object_type;
  if (objectType === 'VIEW') return 'view';
  if (objectType === 'EXTERNAL_TABLE') return 'external';
  return 'table';
}

const push = (map, key, value) => {
  const list = map.get(key) ?? [];
  list.push(value);
  map.set(key, list);
};

/**
 * Full lineage path of one column: walk the column-level TRANSFORMS_TO
 * edges (those carrying source/target handles) upstream to its origins and
 * downstream to its targets, within the loaded graph (i.e. the selected
 * depth). Returns the column ids and edge ids on the path.
 */
export function columnPath(columnId, edges) {
  const cols = new Set([columnId]);
  const edgeIds = new Set();
  if (!columnId) return { cols, edgeIds };

  const down = new Map();   // column id -> edges leaving it
  const up = new Map();     // column id -> edges entering it
  for (const e of edges) {
    if (!e.sourceHandle || !e.targetHandle) continue;
    push(down, e.sourceHandle, e);
    push(up, e.targetHandle, e);
  }

  const walk = (adj, nextOf) => {
    const queue = [columnId];
    const seen = new Set([columnId]);
    while (queue.length) {
      const col = queue.shift();
      for (const e of adj.get(col) ?? []) {
        edgeIds.add(e.id);
        const next = nextOf(e);
        cols.add(next);
        if (!seen.has(next)) {
          seen.add(next);
          queue.push(next);
        }
      }
    }
  };
  walk(down, (e) => e.targetHandle);
  walk(up, (e) => e.sourceHandle);
  return { cols, edgeIds };
}

export function deriveDataFlow(graph) {
  const byId = new Map(graph.nodes.map((n) => [n.id, n]));
  const nodes = graph.nodes.filter((n) => !isProcess(n));

  const edges = [];
  const readsByProcess = new Map();   // process id -> READS_FROM edges into it
  const writesByProcess = new Map();  // process id -> WRITES_TO edges out of it

  for (const e of graph.edges) {
    const source = byId.get(e.source);
    const target = byId.get(e.target);
    if (!source || !target) continue;
    if (!isProcess(source) && !isProcess(target)) {
      edges.push(e);                  // view definitions, column-level edges
    } else if (!isProcess(source) && e.data.edge_type === 'READS_FROM') {
      push(readsByProcess, e.target, e);
    } else if (!isProcess(target) && e.data.edge_type === 'WRITES_TO') {
      push(writesByProcess, e.source, e);
    }
  }

  const seen = new Set();
  for (const [pid, writes] of writesByProcess) {
    for (const read of readsByProcess.get(pid) ?? []) {
      for (const write of writes) {
        const id = `${read.source}>${pid}>${write.target}`;
        if (read.source === write.target || seen.has(id)) continue;
        seen.add(id);
        edges.push({
          id,
          source: read.source,
          target: write.target,
          data: {
            ...write.data,
            edge_type: 'DATA_FLOW',
            via: byId.get(pid)?.name ?? pid,
          },
        });
      }
    }
  }
  return { nodes, edges };
}

export function deriveProcessFlow(graph) {
  const byId = new Map(graph.nodes.map((n) => [n.id, n]));
  const nodes = graph.nodes.filter(isProcess);

  const writersByEntity = new Map();  // entity id -> WRITES_TO edges into it
  const readersByEntity = new Map();  // entity id -> READS_FROM edges out of it
  const edges = [];

  for (const e of graph.edges) {
    const source = byId.get(e.source);
    const target = byId.get(e.target);
    if (!source || !target) continue;
    if (e.data.edge_type === 'EXECUTES' && isProcess(source) && isProcess(target)) {
      edges.push(e);
    } else if (e.data.edge_type === 'WRITES_TO' && isProcess(source)) {
      push(writersByEntity, e.target, e);
    } else if (e.data.edge_type === 'READS_FROM' && isProcess(target)) {
      push(readersByEntity, e.source, e);
    }
  }

  const seen = new Set();
  for (const [entityId, writes] of writersByEntity) {
    for (const write of writes) {
      for (const read of readersByEntity.get(entityId) ?? []) {
        const id = `${write.source}>${entityId}>${read.target}`;
        if (write.source === read.target || seen.has(id)) continue;
        seen.add(id);
        edges.push({
          id,
          source: write.source,
          target: read.target,
          data: {
            edge_type: 'HANDOFF',
            via: byId.get(entityId)?.name ?? entityId,
            transformation: write.data.transformation,
            provenance: write.data.provenance,
            status: write.data.status,
            confidence: write.data.confidence,
            reasoning: write.data.reasoning,
            ai_metadata: write.data.ai_metadata,
          },
        });
      }
    }
  }
  return { nodes, edges };
}
