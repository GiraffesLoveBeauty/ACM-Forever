export function percentile(values, ratio) {
  const sorted = values.filter(Number.isFinite).sort((a, b) => a - b);
  return sorted.length ? sorted[Math.max(0, Math.ceil(sorted.length * ratio) - 1)] : null;
}
export function summarize(rows, field) {
  const values = rows
    .filter((row) => !row.error)
    .map((row) => row[field])
    .filter(Number.isFinite);
  const ordered = [...values].sort((a, b) => a - b);
  const middle = Math.floor(ordered.length / 2);
  return {
    samples: rows.length,
    success: values.length,
    median: ordered.length
      ? ordered.length % 2
        ? ordered[middle]
        : (ordered[middle - 1] + ordered[middle]) / 2
      : null,
    p95: percentile(values, 0.95),
  };
}
export function origin(value) {
  const url = new URL(value);
  if (
    !['http:', 'https:'].includes(url.protocol) ||
    url.username ||
    url.password ||
    url.pathname !== '/' ||
    url.search ||
    url.hash
  )
    throw Error('Provide a site origin without credentials, path or query.');
  return url.origin;
}
export function resourceKind(path) {
  return path.startsWith('/api/') || path === '/health'
    ? 'api'
    : path.startsWith('/assets/')
      ? 'static'
      : 'document';
}
export function phases(timing) {
  const delta = (a, b) => (Number.isFinite(a) && Number.isFinite(b) ? Math.max(0, a - b) : null);
  return {
    dns: delta(timing.domainLookupEnd, timing.domainLookupStart),
    connect: delta(timing.connectEnd, timing.connectStart),
    tls:
      timing.secureConnectionStart > 0 ? delta(timing.connectEnd, timing.secureConnectionStart) : 0,
    ttfb: delta(timing.responseStart, timing.requestStart),
    download: delta(timing.responseEnd, timing.responseStart),
    total: delta(timing.responseEnd, timing.startTime),
  };
}
