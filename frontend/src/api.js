const BASE = '/api';

async function getJSON(path) {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}

export const fetchEntities = () => getJSON('/entities');

export const fetchLineage = (entityId, { depth = 3, level = 'table' } = {}) =>
  getJSON(`/lineage/${encodeURIComponent(entityId)}?depth=${depth}&level=${level}`);
