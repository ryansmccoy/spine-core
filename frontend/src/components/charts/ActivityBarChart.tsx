/**
 * Stacked bar chart showing run activity over time (24h default).
 * Uses Recharts for rendering. Designed for the Dashboard page.
 */

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Legend,
  type TooltipProps,
} from 'recharts';
import { formatChartHour } from '../../lib/formatters';
import { CHART_COLORS } from '../../lib/colors';

export interface RunHistoryBucket {
  timestamp: string;
  completed: number;
  failed: number;
  running: number;
  cancelled: number;
  pending: number;
  total: number;
}

interface ActivityBarChartProps {
  data: RunHistoryBucket[];
  height?: number;
}

function CustomTooltip(props: TooltipProps<number, string>) {
  const { active, payload, label } = props as { active?: boolean; payload?: Array<{ value?: number; color?: string; dataKey?: string; name?: string }>; label?: string };
  if (!active || !payload?.length) return null;
  const ts = label ?? '';
  let dateStr = '';
  try {
    dateStr = new Date(ts).toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    dateStr = ts;
  }
  const total = payload.reduce((sum: number, p: { value?: number }) => sum + ((p.value as number) ?? 0), 0);

  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-lg px-3 py-2 text-xs">
      <p className="font-medium text-gray-700 mb-1">{dateStr}</p>
      {payload.map((p: { dataKey?: string; color?: string; name?: string; value?: number }) => (
        <div key={p.dataKey} className="flex justify-between gap-4">
          <span style={{ color: p.color }}>{p.name}</span>
          <span className="font-mono">{p.value}</span>
        </div>
      ))}
      <div className="border-t border-gray-100 mt-1 pt-1 flex justify-between gap-4 font-medium">
        <span>Total</span>
        <span className="font-mono">{total}</span>
      </div>
    </div>
  );
}

export default function ActivityBarChart({ data, height = 200 }: ActivityBarChartProps) {
  if (!data.length) {
    return (
      <div className="flex items-center justify-center text-sm text-gray-400" style={{ height }}>
        No activity data
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} barCategoryGap="20%" margin={{ top: 5, right: 5, left: -15, bottom: 0 }}>
        <XAxis
          dataKey="timestamp"
          tickFormatter={formatChartHour}
          tick={{ fontSize: 11, fill: '#9ca3af' }}
          axisLine={{ stroke: '#e5e7eb' }}
          tickLine={false}
        />
        <YAxis
          allowDecimals={false}
          tick={{ fontSize: 11, fill: '#9ca3af' }}
          axisLine={false}
          tickLine={false}
        />
        <Tooltip content={<CustomTooltip />} />
        <Legend
          iconSize={8}
          wrapperStyle={{ fontSize: 11, paddingTop: 4 }}
        />
        <Bar dataKey="completed" stackId="a" fill={CHART_COLORS.completed} name="Completed" radius={[0, 0, 0, 0]} />
        <Bar dataKey="failed" stackId="a" fill={CHART_COLORS.failed} name="Failed" />
        <Bar dataKey="running" stackId="a" fill={CHART_COLORS.running} name="Running" />
        <Bar dataKey="cancelled" stackId="a" fill={CHART_COLORS.cancelled} name="Cancelled" radius={[2, 2, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
