/**
 * Shared formatting utilities for timestamps, durations, and numbers.
 */

/**
 * Format milliseconds into a human-readable duration.
 * Examples: "245 ms", "3.2s", "2m 15s", "1h 5m"
 */
export function formatDuration(ms: number | null | undefined): string {
  if (ms == null) return '—';
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  const remainSec = Math.round(seconds % 60);
  if (minutes < 60) return `${minutes}m ${remainSec}s`;
  const hours = Math.floor(minutes / 60);
  const remainMin = minutes % 60;
  return `${hours}h ${remainMin}m`;
}

/**
 * Format ISO timestamp to local date+time string.
 */
export function formatTimestamp(ts: string | null | undefined): string {
  if (!ts) return '—';
  try {
    const d = new Date(ts);
    if (isNaN(d.getTime())) return ts;
    return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'medium' });
  } catch {
    return ts;
  }
}

/**
 * Format ISO timestamp to short local time (HH:MM:SS).
 */
export function formatTime(ts: string | null | undefined): string {
  if (!ts) return '';
  try {
    const d = new Date(ts);
    if (isNaN(d.getTime())) return ts;
    return d.toLocaleTimeString(undefined, {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch {
    return ts;
  }
}

/**
 * Format ISO timestamp to relative time ("2m ago", "1h ago", "3d ago").
 */
export function formatRelativeTime(ts: string | null | undefined): string {
  if (!ts) return '—';
  try {
    const d = new Date(ts);
    if (isNaN(d.getTime())) return ts;
    const now = Date.now();
    const diffMs = now - d.getTime();
    if (diffMs < 0) return 'just now';
    const diffSec = Math.floor(diffMs / 1000);
    if (diffSec < 60) return `${diffSec}s ago`;
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `${diffHr}h ago`;
    const diffDay = Math.floor(diffHr / 24);
    return `${diffDay}d ago`;
  } catch {
    return ts;
  }
}

/**
 * Format a number with comma separators. 1234 → "1,234"
 */
export function formatNumber(n: number): string {
  return n.toLocaleString();
}

/**
 * Format an ISO timestamp for chart x-axis labels (hour-level).
 * Returns "12a", "3p", "6p" etc.
 */
export function formatChartHour(ts: string): string {
  try {
    const d = new Date(ts);
    const h = d.getHours();
    if (h === 0) return '12a';
    if (h === 12) return '12p';
    if (h < 12) return `${h}a`;
    return `${h - 12}p`;
  } catch {
    return '';
  }
}
