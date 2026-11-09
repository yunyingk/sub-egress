export function formatBytes(bytes) {
  if (!bytes || bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

export function formatDate(isoStr) {
  if (!isoStr) return '';
  const d = new Date(isoStr);
  return d.toISOString().split('T')[0];
}

export function maskUrl(url) {
  if (!url) return '';
  if (url.startsWith('local://')) return url;
  try {
    const u = new URL(url);
    return `${u.protocol}//${u.host}/***`;
  } catch {
    return url.substring(0, 30) + '...';
  }
}

export function getTrafficPercent(src) {
  if (!src || !src.traffic_total || src.traffic_total === 0) return 0;
  const pct = ((src.traffic_used || 0) / src.traffic_total) * 100;
  return parseFloat(pct.toFixed(1));
}
