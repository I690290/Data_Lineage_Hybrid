import React from 'react';
import { Handle, Position } from 'reactflow';

import { entityType } from '../graphViews.js';

const TYPE_LABELS = { table: 'TABLE', view: 'VIEW', external: 'EXT TABLE', file: 'FILE' };

/**
 * Data-entity node (Table / View / External table / File): header with a
 * type badge + expandable column list.  Styling is class-driven
 * (`entity-<type>`) so themes live entirely in CSS.  In column drill-down
 * mode each column row exposes its own source/target handles (handle id ==
 * Column node id "OWNER_ID|COL") so TRANSFORMS_TO edges attach to the exact
 * column.
 */
export default function TableNode({ id, data }) {
  const {
    name, columns = [], expanded, onToggle, columnMode,
    focusCols, onColumnClick, dimmed,
  } = data;
  const type = entityType(data);

  return (
    <div className={`table-node entity-${type}${dimmed ? ' node-dim' : ''}`}>
      <Handle type="target" position={Position.Left} className="entity-handle" />
      <Handle type="source" position={Position.Right} className="entity-handle" />

      <div className="table-node-header">
        <span className={`entity-icon icon-${type}`} aria-hidden="true" />
        <span className={`kind-badge badge-${type}`}>{TYPE_LABELS[type]}</span>
        <span className="table-node-name" title={name}>{name}</span>
        {columns.length > 0 && !columnMode && (
          <button
            className="expand-btn"
            onClick={(e) => { e.stopPropagation(); onToggle(id); }}
            title={expanded ? 'Collapse columns' : 'Expand columns'}
          >
            {expanded ? '−' : '+'}
          </button>
        )}
      </div>

      {expanded && (
        <div className="table-node-columns">
          {columns.map((col) => {
            // '*' is the record-level lineage pseudo-column (COBOL READ INTO,
            // no positional guessing); keep its handle id verbatim so the
            // FILE:<dsn>|* edge still attaches, but label it for humans
            const colId = `${id}|${col}`;
            const classes = ['column-row'];
            if (col === '*') classes.push('record-row');
            if (columnMode && onColumnClick) classes.push('col-focusable');
            if (focusCols?.has(colId)) classes.push('col-highlight');
            return (
              <div
                className={classes.join(' ')}
                key={col}
                onClick={columnMode && onColumnClick
                  ? (e) => { e.stopPropagation(); onColumnClick(colId); }
                  : undefined}
                title={columnMode ? 'Click to highlight this column’s lineage path' : undefined}
              >
                <Handle
                  type="target"
                  position={Position.Left}
                  id={colId}
                  className="column-handle"
                />
                <span className="column-name">
                  {col === '*' ? '∗ entire record' : col}
                </span>
                <Handle
                  type="source"
                  position={Position.Right}
                  id={colId}
                  className="column-handle"
                />
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
