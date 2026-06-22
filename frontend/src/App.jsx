import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MarkerType,
  MiniMap,
  useEdgesState,
  useNodesState,
} from 'reactflow';
import 'reactflow/dist/style.css';

import { fetchEntities, fetchLineage } from './api.js';
import { columnPath, deriveDataFlow, deriveProcessFlow, isProcess } from './graphViews.js';
import { layoutGraph } from './layout.js';
import LineageEdge from './components/LineageEdge.jsx';
import ProcessNode from './components/ProcessNode.jsx';
import TableNode from './components/TableNode.jsx';

const nodeTypes = { tableNode: TableNode, processNode: ProcessNode };
const edgeTypes = { lineageEdge: LineageEdge };

// arrowheads are SVG attributes, not CSS, so they carry per-theme values.
// One contract everywhere: blue deterministic, red AI, yellow EXECUTES.
const MARKER_COLORS = {
  light: { AI_INFERRED: '#dc2626', EXECUTES: '#eab308', DEFAULT: '#2563eb' },
  dark: { AI_INFERRED: '#f87171', EXECUTES: '#facc15', DEFAULT: '#60a5fa' },
};

const entityOptionLabel = (e) => {
  if (e.kind === 'Table' && e.attributes?.object_type === 'VIEW') return 'View';
  if (e.kind === 'Table' && e.attributes?.object_type === 'EXTERNAL_TABLE') return 'Ext Table';
  if (e.kind === 'Program') return e.language || 'Program';
  if (e.kind === 'Job') return 'JCL Job';
  return e.kind;
};

const THEME_MODES = ['auto', 'light', 'dark'];

// ---------------------------------------------------------------------------
// Utility: detect SQL vs COBOL from transformation text
// ---------------------------------------------------------------------------
function detectLang(text = '') {
  const t = text.toUpperCase();
  const sqlPatterns = [
    /\bSELECT\s+\w/, /\bINSERT\s+INTO\b/, /\bUPDATE\s+\w+\s+SET\b/,
    /\bDECLARE\s+\w+\s+CURSOR\b/, /\bFETCH\s+\w+\s+INTO\b/,
    /\bEXEC\s+SQL\b/, /\bDSNTIAUL\b/,
  ];
  const cobolPatterns = [
    /\bMOVE\s+\S+\s+TO\b/, /\bCOMPUTE\s+\S+\s*=/, /\bPERFORM\s+/,
    /\bSTRING\s+/, /\bCALL\s+'/, /\bOPEN\s+(INPUT|OUTPUT)\b/,
    /\bREAD\s+\w+\s+INTO\b/,
  ];
  const sqlScore  = sqlPatterns.filter(re => re.test(t)).length;
  const cobolScore = cobolPatterns.filter(re => re.test(t)).length;
  if (sqlScore >= cobolScore && sqlScore > 0) return 'sql';
  if (cobolScore > 0) return 'cobol';
  return 'text';
}

// ---------------------------------------------------------------------------
// TransformationPanel – right-side panel showing full transformation code
// ---------------------------------------------------------------------------
function TransformationPanel({ edge, onClose }) {
  const { data = {} } = edge;
  const code = data.transformation || '';
  const lang = detectLang(code);
  const [copied, setCopied] = useState(false);
  // ordered transformation chain (source -> target); fall back to splitting
  // the joined string so older data still renders as steps
  const steps = (data.transform_steps && data.transform_steps.length)
    ? data.transform_steps
    : (code && code !== 'direct' ? code.split('; ').filter(Boolean) : []);

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [code]);

  const isAI = data.provenance === 'AI_INFERRED';

  return (
    <div className="side-panel">
      {/* ── header ── */}
      <div className="panel-header">
        <div className="panel-title">
          <span className={`prov-chip ${isAI ? 'chip-ai' : 'chip-det'}`}>
            {isAI ? 'AI' : 'DET'}
          </span>
          <span className="panel-edge-type">{data.edge_type}</span>
        </div>
        <button className="panel-close" onClick={onClose} aria-label="Close panel">×</button>
      </div>

      {/* ── column mapping (TRANSFORMS_TO edges) ── */}
      {data.source_column && (
        <div className="panel-section">
          <div className="panel-section-title">Column Mapping</div>
          <div className="panel-col-mapping">
            <span className="panel-col">
              {data.source_column === '*' ? '(entire record)' : data.source_column}
            </span>
            <span className="panel-arrow">→</span>
            <span className="panel-col">
              {data.target_column === '*' ? '(entire record)' : data.target_column}
            </span>
          </div>
        </div>
      )}

      {/* ── via program / dataset ── */}
      {(data.program || data.via) && (
        <div className="panel-meta">
          {data.via ? `dataset ${data.via}` : `via ${data.program}`}
        </div>
      )}

      {/* ── AI-specific metadata ── */}
      {isAI && (
        <div className="panel-section panel-ai-section">
          <div className="panel-ai-row">
            <span className="panel-confidence">
              {Math.round((data.confidence ?? 0) * 100)}% confidence
            </span>
            {data.status && (
              <span className="panel-status">{data.status}</span>
            )}
          </div>
          {data.reasoning && (
            <div className="panel-reasoning">{data.reasoning}</div>
          )}
          {data.ai_metadata?.model && (
            <div className="panel-model">
              Model: {data.ai_metadata.model}
              {data.ai_metadata.judge_rationale && (
                <> · Judge: {data.ai_metadata.judge_rationale}</>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── transformation chain (ordered source -> target) ── */}
      {steps.length > 1 && (
        <div className="panel-section">
          <div className="panel-section-title">
            Transformation chain ({steps.length} steps, source → target)
          </div>
          <ol className="panel-steps">
            {steps.map((s, i) => (
              <li key={i} className="panel-step"><code>{s}</code></li>
            ))}
          </ol>
        </div>
      )}

      {/* ── transformation code (full, copyable) ── */}
      {code && (
        <div className="panel-section panel-code-section">
          <div className="panel-code-header">
            <span className="panel-code-lang">{lang.toUpperCase()}</span>
            <button
              className={`panel-copy-btn${copied ? ' copied' : ''}`}
              onClick={handleCopy}
            >
              {copied ? '✓ Copied' : 'Copy'}
            </button>
          </div>
          <pre className="panel-code">{code}</pre>
        </div>
      )}

      {/* ── source evidence (AI edges only) ── */}
      {data.evidence && isAI && (
        <details className="panel-section panel-evidence">
          <summary className="panel-section-title">Source Evidence</summary>
          <pre className="panel-code panel-evidence-code">{data.evidence}</pre>
        </details>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// App
// ---------------------------------------------------------------------------
export default function App() {
  const [entities, setEntities] = useState([]);
  const [selected, setSelected] = useState('');
  const [depth, setDepth] = useState(3);
  const [tab, setTab] = useState('data');          // 'data' | 'process'
  const [level, setLevel] = useState('table');     // 'table' | 'column' drill-down
  const [graph, setGraph] = useState({ nodes: [], edges: [] });
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'auto');
  const [resolvedTheme, setResolvedTheme] = useState(
    () => document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light');

  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const rfInstance = useRef(null);

  useEffect(() => {
    localStorage.setItem('theme', theme);
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const apply = () => {
      const dark = theme === 'dark' || (theme === 'auto' && mq.matches);
      document.documentElement.dataset.theme = dark ? 'dark' : 'light';
      setResolvedTheme(dark ? 'dark' : 'light');
    };
    apply();
    if (theme === 'auto') {
      mq.addEventListener('change', apply);
      return () => mq.removeEventListener('change', apply);
    }
  }, [theme]);

  useEffect(() => {
    fetchEntities()
      .then((list) => setEntities(list))
      .catch((e) => setError(String(e)));
  }, []);

  // Data Lineage picks among data entities (tables / views / files);
  // Process Lineage among processes (programs / jobs / scripts)
  const options = useMemo(
    () => entities.filter((e) => isProcess(e) === (tab === 'process')),
    [entities, tab],
  );

  useEffect(() => {
    if (options.length && !options.some((e) => e.id === selected)) {
      const first = tab === 'data'
        ? options.find((e) => e.kind === 'Table') ?? options[0]
        : options[0];
      setSelected(first.id);
    }
  }, [options, selected, tab]);

  // column drill-down only makes sense entity-to-entity
  const effectiveLevel = tab === 'data' ? level : 'table';

  useEffect(() => {
    if (!selected) return;
    setLoading(true);
    fetchLineage(selected, { depth, level: effectiveLevel })
      .then((data) => { setGraph(data); setError(null); })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [selected, depth, effectiveLevel]);

  const onToggle = useCallback((id) => {
    setNodes((nds) => nds.map((n) =>
      n.id === id ? { ...n, data: { ...n.data, expanded: !n.data.expanded } } : n));
  }, [setNodes]);

  // column path highlighting: clicking a column (drill-down mode) selects it
  const [focusCol, setFocusCol] = useState(null);
  const onColumnClick = useCallback((colId) => {
    setFocusCol((cur) => (cur === colId ? null : colId));
  }, []);

  // transformation side panel: clicking an edge opens it
  const [selectedEdge, setSelectedEdge] = useState(null);
  const onEdgeClick = useCallback((_evt, edge) => {
    setSelectedEdge((cur) => (cur?.id === edge.id ? null : edge));
  }, []);

  // clear side panel when the graph view is replaced
  useEffect(() => { setSelectedEdge(null); }, [graph]);

  const view = useMemo(
    () => (tab === 'data' ? deriveDataFlow(graph) : deriveProcessFlow(graph)),
    [graph, tab],
  );

  // a new graph / view invalidates any column selection
  useEffect(() => { setFocusCol(null); }, [view, effectiveLevel]);

  const fitSoon = useCallback(() => {
    requestAnimationFrame(() =>
      rfInstance.current?.fitView({ padding: 0.15, duration: 300 }));
  }, []);

  // (re)build + auto-layout whenever the derived view changes; afterwards
  // nodes stay free-form draggable (onNodesChange applies drag deltas)
  useEffect(() => {
    const columnMode = effectiveLevel === 'column';
    const markers = MARKER_COLORS[resolvedTheme];
    const flowNodes = view.nodes.map((n) => ({
      id: n.id,
      type: isProcess(n) ? 'processNode' : 'tableNode',
      data: { ...n, columnMode, expanded: columnMode, onToggle, onColumnClick },
      position: { x: 0, y: 0 },
    }));
    const flowEdges = view.edges.map((e) => ({
      ...e,
      type: 'lineageEdge',
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: e.data.provenance === 'AI_INFERRED' ? markers.AI_INFERRED
          : markers[e.data.edge_type] ?? markers.DEFAULT,
      },
    }));
    setNodes(layoutGraph(flowNodes, flowEdges));
    setEdges(flowEdges);
    fitSoon();
  }, [view, effectiveLevel, resolvedTheme, onToggle, onColumnClick,
      setNodes, setEdges, fitSoon]);

  // apply / clear the highlighted column path without re-laying out
  useEffect(() => {
    const { cols, edgeIds } = columnPath(focusCol, view.edges);
    setEdges((eds) => eds.map((e) => ({
      ...e,
      data: {
        ...e.data,
        hot: focusCol ? edgeIds.has(e.id) : false,
        dim: focusCol ? !edgeIds.has(e.id) : false,
      },
    })));
    setNodes((nds) => nds.map((n) => {
      const onPath = focusCol
        && (n.data.columns ?? []).some((c) => cols.has(`${n.id}|${c}`));
      return {
        ...n,
        data: {
          ...n.data,
          focusCols: focusCol ? cols : null,
          dimmed: focusCol ? !onPath : false,
        },
      };
    }));
  }, [focusCol, view, setEdges, setNodes]);

  // re-run auto-layout on demand (after manual dragging / expanding)
  const relayout = useCallback(() => {
    setNodes((nds) => layoutGraph(nds, edges));
    fitSoon();
  }, [edges, setNodes, fitSoon]);

  const clearSelections = useCallback(() => {
    setFocusCol(null);
    setSelectedEdge(null);
  }, []);

  return (
    <div className="app">
      <header className="toolbar">
        <h1>The Data Journey</h1>

        <nav className="view-tabs" aria-label="Lineage perspective">
          <button
            className={tab === 'data' ? 'active' : ''}
            onClick={() => setTab('data')}
          >
            Data Lineage
          </button>
          <button
            className={tab === 'process' ? 'active' : ''}
            onClick={() => setTab('process')}
          >
            Process Lineage
          </button>
        </nav>

        <label>
          {tab === 'data' ? 'Entity' : 'Process/Program'}
          <select value={selected} onChange={(e) => setSelected(e.target.value)}>
            {options.map((e) => (
              <option key={e.id} value={e.id}>
                [{entityOptionLabel(e)}] {e.name}
              </option>
            ))}
          </select>
        </label>

        <label>
          Depth
          <input
            type="number" min="1" max="8" value={depth}
            onChange={(e) => setDepth(Number(e.target.value))}
          />
        </label>

        <div className="level-toggle">
          <button
            className={level === 'table' ? 'active' : ''}
            onClick={() => setLevel('table')}
            disabled={tab !== 'data'}
          >
            Entity Lineage
          </button>
          <button
            className={level === 'column' ? 'active' : ''}
            onClick={() => setLevel('column')}
            disabled={tab !== 'data'}
            title={tab !== 'data' ? 'Column Lineage is available in Data Lineage' : ''}
          >
            Column Lineage
          </button>
        </div>

        <button className="relayout-btn" onClick={relayout} title="Auto-arrange nodes">
          ⟲ Re-layout
        </button>

        <div className="theme-toggle" role="group" aria-label="Color theme">
          {THEME_MODES.map((mode) => (
            <button
              key={mode}
              className={theme === mode ? 'active' : ''}
              onClick={() => setTheme(mode)}
              title={mode === 'auto' ? 'Follow system setting' : `${mode} mode`}
            >
              {mode === 'auto' ? 'Auto' : mode === 'light' ? '☀ Light' : '☾ Dark'}
            </button>
          ))}
        </div>

        <div className="legend">
          <span><i className="line det" /> DETERMINISTIC (data flow)</span>
          <span><i className="line ai" /> AI_INFERRED (provisional)</span>
          <span><i className="line exec" /> EXECUTES (control flow)</span>
        </div>
        {loading && <span className="loading">loading…</span>}
      </header>

      {error && <div className="error-banner">{error}</div>}

      <div className="main-area">
        <div className="canvas">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onInit={(instance) => { rfInstance.current = instance; }}
            onPaneClick={clearSelections}
            onEdgeClick={onEdgeClick}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            nodesDraggable
            nodesConnectable={false}
            panOnDrag
            zoomOnScroll
            zoomOnPinch
            fitView
            proOptions={{ hideAttribution: true }}
            minZoom={0.2}
          >
            <Background gap={18} />
            <Controls />
            <MiniMap pannable zoomable />
          </ReactFlow>
        </div>

        {selectedEdge && (
          <TransformationPanel
            edge={selectedEdge}
            onClose={() => setSelectedEdge(null)}
          />
        )}
      </div>
    </div>
  );
}
