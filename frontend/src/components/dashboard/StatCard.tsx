/**
 * Metric stat card with optional trend indicator.
 * Displays a single KPI value with title and optional color accent.
 */

import {
  Activity,
  CheckCircle2,
  XCircle,
  Play,
  AlertTriangle,
  type LucideIcon,
} from 'lucide-react';

interface StatCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon?: LucideIcon;
  color?: 'blue' | 'green' | 'red' | 'yellow' | 'gray' | 'orange' | 'purple';
  trend?: { direction: 'up' | 'down' | 'flat'; label: string };
}

const ACCENT: Record<string, { border: string; icon: string; trendUp: string; trendDown: string }> = {
  blue:   { border: 'border-l-blue-500',   icon: 'text-blue-500',   trendUp: 'text-blue-600',   trendDown: 'text-blue-400' },
  green:  { border: 'border-l-green-500',  icon: 'text-green-500',  trendUp: 'text-green-600',  trendDown: 'text-green-400' },
  red:    { border: 'border-l-red-500',    icon: 'text-red-500',    trendUp: 'text-red-600',    trendDown: 'text-red-400' },
  yellow: { border: 'border-l-yellow-500', icon: 'text-yellow-500', trendUp: 'text-yellow-600', trendDown: 'text-yellow-400' },
  gray:   { border: 'border-l-gray-400',   icon: 'text-gray-400',   trendUp: 'text-gray-600',   trendDown: 'text-gray-400' },
  orange: { border: 'border-l-orange-500', icon: 'text-orange-500', trendUp: 'text-orange-600', trendDown: 'text-orange-400' },
  purple: { border: 'border-l-purple-500', icon: 'text-purple-500', trendUp: 'text-purple-600', trendDown: 'text-purple-400' },
};

export default function StatCard({ title, value, subtitle, icon: Icon, color = 'blue', trend }: StatCardProps) {
  const accent = ACCENT[color] ?? ACCENT.blue;

  return (
    <div className={`bg-white rounded-lg shadow-sm border border-gray-200 border-l-4 ${accent.border} p-4`}>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{title}</p>
          <p className="mt-1 text-2xl font-bold text-gray-900">{value}</p>
          {subtitle && <p className="mt-0.5 text-xs text-gray-400">{subtitle}</p>}
          {trend && (
            <p className={`mt-1 text-xs font-medium ${trend.direction === 'up' ? accent.trendUp : trend.direction === 'down' ? accent.trendDown : 'text-gray-400'}`}>
              {trend.direction === 'up' ? '↑' : trend.direction === 'down' ? '↓' : '→'} {trend.label}
            </p>
          )}
        </div>
        {Icon && (
          <div className={`p-2 rounded-lg bg-gray-50 ${accent.icon}`}>
            <Icon size={20} />
          </div>
        )}
      </div>
    </div>
  );
}

/** Pre-configured stat card row showing run status counts */
export function StatusCardRow({
  stats,
  dlqCount,
}: {
  stats: { total: number; running: number; failed: number; completed: number; pending: number };
  dlqCount?: number;
}) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
      <StatCard
        title="Total Runs"
        value={stats.total.toLocaleString()}
        icon={Activity}
        color="blue"
      />
      <StatCard
        title="Running"
        value={stats.running}
        icon={Play}
        color="blue"
      />
      <StatCard
        title="Completed"
        value={stats.completed.toLocaleString()}
        icon={CheckCircle2}
        color="green"
      />
      <StatCard
        title="Failed"
        value={stats.failed}
        icon={XCircle}
        color="red"
      />
      <StatCard
        title="Dead Letters"
        value={dlqCount ?? 0}
        icon={AlertTriangle}
        color={dlqCount && dlqCount > 0 ? 'orange' : 'gray'}
      />
    </div>
  );
}
