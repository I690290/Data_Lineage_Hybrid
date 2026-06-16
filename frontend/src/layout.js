import dagre from '@dagrejs/dagre';

const TABLE_WIDTH = 280;
const PROCESS_WIDTH = 200;
const HEADER_HEIGHT = 54;
const ROW_HEIGHT = 24;

export function nodeDimensions(node) {
  if (node.type === 'processNode') return { width: PROCESS_WIDTH, height: 48 };
  const rows = node.data.expanded ? (node.data.columns?.length ?? 0) : 0;
  return { width: TABLE_WIDTH, height: HEADER_HEIGHT + rows * ROW_HEIGHT + 8 };
}

export function layoutGraph(nodes, edges) {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: 'LR', nodesep: 48, ranksep: 130 });
  g.setDefaultEdgeLabel(() => ({}));

  nodes.forEach((n) => g.setNode(n.id, nodeDimensions(n)));
  edges.forEach((e) => g.setEdge(e.source, e.target));
  dagre.layout(g);

  return nodes.map((n) => {
    const { x, y } = g.node(n.id);
    const { width, height } = nodeDimensions(n);
    return { ...n, position: { x: x - width / 2, y: y - height / 2 } };
  });
}
