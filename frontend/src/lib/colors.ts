/**
 * Centralized state → color mapping for consistent status visualization.
 * Used by StatusBadge, StepNode, WorkflowDAG, and dashboard components.
 */

export type RunStatus =
  | 'pending'
  | 'queued'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'dead_lettered'
  | 'retrying'
  | 'PENDING'
  | 'RUNNING'
  | 'COMPLETED'
  | 'FAILED'
  | 'SKIPPED';

export interface StatusStyle {
  bg: string;
  text: string;
  border: string;
  dot: string;
  /** Extra Tailwind classes (e.g. animate-pulse) */
  extra?: string;
}

const STATUS_MAP: Record<string, StatusStyle> = {
  // Run-level statuses
  pending:        { bg: 'bg-gray-100',    text: 'text-gray-600',    border: 'border-gray-300',   dot: 'bg-gray-400' },
  queued:         { bg: 'bg-yellow-50',   text: 'text-yellow-700',  border: 'border-yellow-400', dot: 'bg-yellow-500' },
  running:        { bg: 'bg-blue-50',     text: 'text-blue-700',    border: 'border-blue-500',   dot: 'bg-blue-500', extra: 'animate-pulse' },
  completed:      { bg: 'bg-green-50',    text: 'text-green-700',   border: 'border-green-500',  dot: 'bg-green-500' },
  failed:         { bg: 'bg-red-50',      text: 'text-red-700',     border: 'border-red-500',    dot: 'bg-red-500' },
  cancelled:      { bg: 'bg-gray-50',     text: 'text-gray-500',    border: 'border-gray-400',   dot: 'bg-gray-400' },
  dead_lettered:  { bg: 'bg-orange-50',   text: 'text-orange-700',  border: 'border-orange-500', dot: 'bg-orange-500' },
  retrying:       { bg: 'bg-purple-50',   text: 'text-purple-700',  border: 'border-purple-400', dot: 'bg-purple-500' },

  // Step-level statuses (uppercase from API)
  PENDING:   { bg: 'bg-gray-100',  text: 'text-gray-600',  border: 'border-gray-300',  dot: 'bg-gray-400' },
  RUNNING:   { bg: 'bg-blue-50',   text: 'text-blue-700',  border: 'border-blue-500',  dot: 'bg-blue-500', extra: 'animate-pulse' },
  COMPLETED: { bg: 'bg-green-50',  text: 'text-green-700', border: 'border-green-500', dot: 'bg-green-500' },
  FAILED:    { bg: 'bg-red-50',    text: 'text-red-700',   border: 'border-red-500',   dot: 'bg-red-500' },
  SKIPPED:   { bg: 'bg-gray-50',   text: 'text-gray-400',  border: 'border-gray-200',  dot: 'bg-gray-300' },
};

const DEFAULT_STYLE: StatusStyle = {
  bg: 'bg-gray-100', text: 'text-gray-600', border: 'border-gray-300', dot: 'bg-gray-400',
};

export function getStatusStyle(status: string | undefined): StatusStyle {
  if (!status) return DEFAULT_STYLE;
  return STATUS_MAP[status] ?? STATUS_MAP[status.toLowerCase()] ?? DEFAULT_STYLE;
}

/** Get the hex color for Recharts / SVG usage */
export function getStatusHex(status: string): string {
  const map: Record<string, string> = {
    completed: '#22c55e',
    COMPLETED: '#22c55e',
    failed:    '#ef4444',
    FAILED:    '#ef4444',
    running:   '#3b82f6',
    RUNNING:   '#3b82f6',
    pending:   '#9ca3af',
    PENDING:   '#9ca3af',
    cancelled: '#6b7280',
    SKIPPED:   '#d1d5db',
    dead_lettered: '#f97316',
    retrying:  '#a855f7',
  };
  return map[status] ?? '#9ca3af';
}

/** Recharts-friendly color palette for stacked charts */
export const CHART_COLORS = {
  completed: '#22c55e',
  failed:    '#ef4444',
  running:   '#3b82f6',
  cancelled: '#9ca3af',
  pending:   '#fbbf24',
} as const;
