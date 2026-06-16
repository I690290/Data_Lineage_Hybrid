import React, { useState } from 'react';
import { BaseEdge, EdgeLabelRenderer, getBezierPath } from 'reactflow';

/**
 * Lineage edge with provenance styling + transformation tooltip on hover.
 * One color contract across every view:
 *   DETERMINISTIC      -> solid blue   (data flow proven from source code)
 *   AI_INFERRED        -> dashed red   (PROVISIONAL until reviewed)
 *   EXECUTES           -> yellow       (control flow: job/program runs program)
 * Derived edges (DATA_FLOW / HANDOFF) inherit the provenance color of the
 * movement they collapse. Colors come from CSS custom properties
 * (styles.css :root) so themes are CSS-driven.
 * `data.hot` / `data.dim` implement column-path highlighting.
 */
export default function LineageEdge(props) {
  const {
    id, sourceX, sourceY, targetX, targetY,
    sourcePosition, targetPosition, data = {}, markerEnd,
  } = props;
  const [hovered, setHovered] = useState(false);

  const [path, labelX, labelY] = getBezierPath({
    sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition,
  });

  const ai = data.provenance === 'AI_INFERRED';
  const executes = data.edge_type === 'EXECUTES';
  const handoff = data.edge_type === 'HANDOFF';
  const stroke = ai ? 'var(--edge-ai)'
    : executes ? 'var(--edge-exec)'
    : 'var(--edge-det)';

  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        markerEnd={markerEnd}
        style={{
          stroke,
          strokeWidth: hovered || data.hot ? 3 : executes ? 1.4 : 2,
          strokeDasharray: ai ? '7 5' : undefined,
          opacity: data.dim ? 0.12 : 1,
        }}
      />
      {/* fat invisible path so hovering is easy */}
      <path
        d={path}
        fill="none"
        stroke="transparent"
        strokeWidth={16}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
      />
      <EdgeLabelRenderer>
        {handoff && data.via && !hovered && !data.dim && (
          <div
            className="edge-via-label"
            style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)` }}
          >
            {data.via}
          </div>
        )}
        {ai && !hovered && !data.dim && data.confidence != null && (
          <div
            className="edge-conf-badge"
            title="AI-inferred (provisional) - judge confidence"
            style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)` }}
          >
            AI {Math.round(data.confidence * 100)}%
          </div>
        )}
        {hovered && (
          <div
            className="edge-tooltip"
            style={{ transform: `translate(-50%, -110%) translate(${labelX}px, ${labelY}px)` }}
          >
            <div className="tooltip-row">
              <span className={`prov-chip ${ai ? 'chip-ai' : 'chip-det'}`}>
                {data.provenance || 'DETERMINISTIC'}
              </span>
              <span className="tooltip-type">{data.edge_type}</span>
              {ai && (
                <span className="status-chip">
                  {data.status} · confidence {Math.round((data.confidence ?? 0) * 100)}%
                </span>
              )}
            </div>
            {ai && data.reasoning && (
              <div className="tooltip-reasoning">{data.reasoning}</div>
            )}
            {data.source_column && (
              <div className="tooltip-cols">
                {data.source_column === '*' ? '(entire record)' : data.source_column}
                {' → '}
                {data.target_column === '*' ? '(entire record)' : data.target_column}
              </div>
            )}
            {data.transformation && (
              <pre className="tooltip-logic">{data.transformation}</pre>
            )}
            {data.via && (
              <div className="tooltip-program">
                {handoff ? `dataset ${data.via}` : `via ${data.via}`}
              </div>
            )}
            {!data.via && data.program && (
              <div className="tooltip-program">via {data.program}</div>
            )}
            {ai && data.ai_metadata?.model && (
              <div className="tooltip-program">
                model {data.ai_metadata.model}
                {data.ai_metadata.judge_rationale &&
                  ` · judge: ${data.ai_metadata.judge_rationale}`}
              </div>
            )}
          </div>
        )}
      </EdgeLabelRenderer>
    </>
  );
}
