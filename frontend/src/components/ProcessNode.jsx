import React from 'react';
import { Handle, Position } from 'reactflow';

/** Sub-label: where this process lives in the estate (step, object type). */
function processDetail({ kind, language, attributes = {} }) {
  if (kind === 'Job') return 'JCL JOB';
  if (attributes.utility) {
    return `${attributes.utility} · ${attributes.job ?? ''} ${attributes.step ?? ''}`.trim();
  }
  if (attributes.object_type === 'PROCEDURE') return 'PL/SQL PROCEDURE';
  if (attributes.object_type === 'EXTERNAL_TABLE_LOADER') return 'ORACLE LOADER';
  return language || 'PROGRAM';
}

/**
 * Process node: JCL jobs & utility steps, COBOL programs, PL/SQL procedures,
 * Oracle loaders.  Visually distinct from data entities (pill shape) and
 * themed per runtime via `process-<language>` CSS classes.
 */
export default function ProcessNode({ data }) {
  const { name, kind, language } = data;
  const langClass = (language || kind).toLowerCase().replace(/[^a-z0-9]+/g, '-');
  return (
    <div className={`process-node process-${langClass} ${kind === 'Job' ? 'job-node' : ''}`}>
      <Handle type="target" position={Position.Left} className="entity-handle" />
      <span className={`process-icon ${kind === 'Job' ? 'icon-job' : 'icon-program'}`} aria-hidden="true" />
      <div className="process-body">
        <span className="process-name" title={name}>{name}</span>
        <span className="process-lang">{processDetail(data)}</span>
      </div>
      <Handle type="source" position={Position.Right} className="entity-handle" />
    </div>
  );
}
