/**
 * Gantt-style horizontal bar chart showing step timing waterfall.
 * Uses Recharts BarChart with custom bars for each step.
 */

import { useMemo } from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import type { RunStep } from '../../types/api';
import { getStatusHex } from '../../lib/colors';
import { formatDuration } from '../../lib/formatters';

interface StepGanttChartProps {
  steps: RunStep[];
  height?: number;
}

interface GanttRow {
  name: string;
  start: number;
  duration: number;
  status: string;
  rawStart: string | null;
  rawEnd: string | null;
}

export default function StepGanttChart({ steps, height = 300 }: StepGanttChartProps) {
  const { data, maxMs } = useMemo(() => {
    if (!steps.length) return { data: [], maxMs: 0 };

    // Find the earliest start time as baseline
    const starts = steps
      .filter((s) => s.started_at)
      .map((s) => new Date(s.started_at!).getTime());

    if (starts.length === 0) return { data: [], maxMs: 0 };
    const baseline = Math.min(...starts);

    const rows: GanttRow[] = steps
      .sort((a, b) => (a.step_order ?? 0) - (b.step_order ?? 0))
      .map((s) => {
        const startMs = s.started_at ? new Date(s.started_at).getTime() - baseline : 0;
        const dur = s.duration_ms ?? 0;
        return {
          name: s.step_name,
          start: startMs,
          duration: dur,
          status: s.status,
          rawStart: s.started_at,
          rawEnd: s.completed_at,
        };
      });

    const maxMs = Math.max(...rows.map((r) => r.start + r.duration), 1);
    return { data: rows, maxMs };
  }, [steps]);

  if (data.length === 0) return null;

  return (
    <div>
      <h4 className="text-xs font-medium text-gray-500 mb-2">Step Timing Waterfall</h4>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart
          data={data}
          layout="vertical"
          margin={{ top: 5, right: 30, left: 10, bottom: 5 }}
          barCategoryGap="20%"
        >
          <CartesianGrid strokeDasharray="3 3" horizontal={false} />
          <XAxis
            type="number"
            domain={[0, maxMs]}
            tickFormatter={(v) => formatDuration(v)}
            tick={{ fontSize: 10 }}
          />
          <YAxis
            type="category"
            dataKey="name"
            width={120}
            tick={{ fontSize: 11 }}
          />
          <Tooltip
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const d = payload[0].payload as GanttRow;
              return (
                <div className="bg-white border border-gray-200 rounded-lg shadow-lg p-3 text-xs">
                  <p className="font-medium text-gray-900">{d.name}</p>
                  <p className="text-gray-500">Status: {d.status}</p>
                  <p className="text-gray-500">Offset: {formatDuration(d.start)}</p>
                  <p className="text-gray-500">Duration: {formatDuration(d.duration)}</p>
                </div>
              );
            }}
          />
          {/* Invisible bar for the start offset */}
          <Bar dataKey="start" stackId="a" fill="transparent" />
          {/* Visible bar for the duration */}
          <Bar dataKey="duration" stackId="a" radius={[0, 4, 4, 0]}>
            {data.map((entry, idx) => (
              <Cell key={idx} fill={getStatusHex(entry.status)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
