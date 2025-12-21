import { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Activity,
  CheckCircle2,
  XCircle,
  Play,
  AlertTriangle,
  Clock,
  Cpu,
  Database,
  ArrowUpRight,
  CircleDot,
} from 'lucide-react';
import PageHeader from '../components/PageHeader';
import StatusBadge from '../components/StatusBadge';
import { Spinner, ErrorBox } from '../components/UI';
import { ActivityBarChart } from '../components/charts';
import { formatDuration, formatRelativeTime } from '../lib/formatters';
import {
  useHealth,
  useDatabaseHealth,
  useRuns,
  useRunStats,
  useRunHistory,
  useQueueDepths,
  useWorkers,
  useDLQ,
} from '../api/hooks';

const TIME_RANGES = [
  { label: '1h', hours: 1, buckets: 12 },
  { label: '6h', hours: 6, buckets: 12 },
  { label: '24h', hours: 24, buckets: 24 },
  { label: '7d', hours: 168, buckets: 28 },
] as const;

function MiniStatCard({
  label,
  value,
  icon: Icon,
  color,
  href,
}: {
  label: string;
  value: string | number;
  icon: React.ElementType;
  color: string;
  href?: string;
}) {
  const inner = (
    <div className={`bg-white rounded-xl border border-gray-200/80 p-5 hover:shadow-md transition-all duration-200 group ${href ? 'cursor-pointer' : ''}`}>
      <div className="flex items-start justify-between">
        <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${color}`}>
          <Icon size={20} />
        </div>
        {href && (
          <ArrowUpRight size={14} className="text-gray-300 group-hover:text-gray-500 transition-colors" />
        )}
      </div>
      <p className="mt-3 text-2xl font-semibold text-gray-900 tabular-nums">{value}</p>
      <p className="mt-0.5 text-xs font-medium text-gray-500">{label}</p>
    </div>
  );
  return href ? <Link to={href}>{inner}</Link> : inner;
}

export default function Dashboard() {
  const [timeRange, setTimeRange] = useState(2); // default 24h
  const health = useHealth();
  const db = useDatabaseHealth();
  const stats = useRunStats();
  const history = useRunHistory({
    hours: TIME_RANGES[timeRange].hours,
    buckets: TIME_RANGES[timeRange].buckets,
  });
  const queues = useQueueDepths();
  const workers = useWorkers();
  const runs = useRuns({ limit: 8 });
  const dlq = useDLQ({ limit: 1 });

  if (health.isLoading) return <Spinner />;
  if (health.isError) return <ErrorBox message="Cannot reach spine-core API" />;

  const h = health.data?.data;
  const d = db.data?.data;
  const s = stats.data?.data;
  const workerList = workers.data?.data ?? [];
  const dlqCount = dlq.data?.page?.total ?? s?.dead_lettered ?? 0;
  const queueData = queues.data?.data ?? [];

  const successRate = s && s.total > 0
    ? ((s.completed / s.total) * 100).toFixed(1)
    : '—';

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="System health, activity, and recent runs at a glance"
      />

      {/* KPI Cards Row — Prefect-style with icons and links */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        <MiniStatCard
          label="Total Runs"
          value={(s?.total ?? 0).toLocaleString()}
          icon={Activity}
          color="bg-spine-50 text-spine-600"
          href="/runs"
        />
        <MiniStatCard
          label="Running"
          value={s?.running ?? 0}
          icon={Play}
          color="bg-blue-50 text-blue-600"
          href="/runs?status=running"
        />
        <MiniStatCard
          label="Completed"
          value={(s?.completed ?? 0).toLocaleString()}
          icon={CheckCircle2}
          color="bg-emerald-50 text-emerald-600"
          href="/runs?status=completed"
        />
        <MiniStatCard
          label="Failed"
          value={s?.failed ?? 0}
          icon={XCircle}
          color="bg-red-50 text-red-600"
          href="/runs?status=failed"
        />
        <MiniStatCard
          label="Success Rate"
          value={successRate === '—' ? '—' : `${successRate}%`}
          icon={CircleDot}
          color="bg-violet-50 text-violet-600"
        />
        <MiniStatCard
          label="Dead Letters"
          value={dlqCount}
          icon={AlertTriangle}
          color={dlqCount > 0 ? 'bg-orange-50 text-orange-600' : 'bg-gray-50 text-gray-400'}
          href="/dlq"
        />
      </div>

      {/* Activity chart + System health */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mt-6">
        {/* Activity chart — main panel */}
        <div className="lg:col-span-2 bg-white rounded-xl border border-gray-200/80 p-5">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-sm font-semibold text-gray-800">Run Activity</h3>
              <p className="text-xs text-gray-400 mt-0.5">Execution history by status</p>
            </div>
            <div className="flex gap-0.5 bg-gray-100 rounded-lg p-0.5">
              {TIME_RANGES.map((tr, i) => (
                <button
                  key={tr.label}
                  onClick={() => setTimeRange(i)}
                  className={`px-2.5 py-1 text-xs font-medium rounded-md transition-all ${
                    timeRange === i
                      ? 'bg-white text-gray-900 shadow-sm'
                      : 'text-gray-500 hover:text-gray-700'
                  }`}
                >
                  {tr.label}
                </button>
              ))}
            </div>
          </div>
          <ActivityBarChart
            data={(history.data?.data ?? []).map(b => ({
              timestamp: b.bucket,
              completed: b.completed,
              failed: b.failed,
              running: b.running,
              cancelled: b.cancelled,
              pending: 0,
              total: b.completed + b.failed + b.running + b.cancelled,
            }))}
            height={260}
          />
        </div>

        {/* Right sidebar: System health + Queue depths */}
        <div className="space-y-4">
          {/* System health card */}
          <div className="bg-white rounded-xl border border-gray-200/80 p-5">
            <h3 className="text-sm font-semibold text-gray-800 mb-4">System Health</h3>
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div className={`w-2 h-2 rounded-full ${h?.status === 'healthy' || h?.status === 'alive' ? 'bg-emerald-500' : 'bg-red-500'}`} />
                  <span className="text-sm text-gray-700">API</span>
                </div>
                <span className="text-xs font-medium text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-md">
                  {h?.status ?? 'unknown'}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <Database size={14} className="text-gray-400" />
                  <span className="text-sm text-gray-700">Database</span>
                </div>
                <span className="text-xs text-gray-500">
                  {d?.backend ?? '—'} · {d?.latency_ms?.toFixed(0) ?? '—'}ms
                </span>
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <Cpu size={14} className="text-gray-400" />
                  <span className="text-sm text-gray-700">Workers</span>
                </div>
                <span className={`text-xs font-medium px-2 py-0.5 rounded-md ${workerList.length > 0 ? 'bg-emerald-50 text-emerald-600' : 'bg-gray-100 text-gray-500'}`}>
                  {workerList.length} active
                </span>
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <Clock size={14} className="text-gray-400" />
                  <span className="text-sm text-gray-700">Pending</span>
                </div>
                <span className="text-xs text-gray-500">{s?.pending ?? 0} in queue</span>
              </div>
            </div>
          </div>

          {/* Queue depths */}
          {queueData.length > 0 && (
            <div className="bg-white rounded-xl border border-gray-200/80 p-5">
              <h3 className="text-sm font-semibold text-gray-800 mb-3">Queue Depths</h3>
              <div className="space-y-2">
                {queueData.map((q) => {
                  const total = q.pending + q.running;
                  return (
                    <div key={q.lane}>
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs text-gray-600 font-medium truncate">{q.lane}</span>
                        <span className="text-xs tabular-nums text-gray-500">{q.pending} pending · {q.running} running</span>
                      </div>
                      {total > 0 && (
                        <div className="w-full h-1.5 bg-gray-100 rounded-full overflow-hidden">
                          <div
                            className="h-full rounded-full transition-all bg-spine-500"
                            style={{ width: `${Math.min((q.running / Math.max(total, 1)) * 100, 100)}%` }}
                          />
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Recent runs table */}
      <div className="bg-white rounded-xl border border-gray-200/80 mt-6 overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
          <div>
            <h3 className="text-sm font-semibold text-gray-800">Recent Runs</h3>
            <p className="text-xs text-gray-400 mt-0.5">Latest execution activity</p>
          </div>
          <Link
            to="/runs"
            className="text-xs font-medium text-spine-600 hover:text-spine-700 transition-colors flex items-center gap-1"
          >
            View all <ArrowUpRight size={12} />
          </Link>
        </div>
        {runs.data?.data?.length ? (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-gray-500 bg-gray-50/50">
                <th className="px-5 py-2.5 font-medium">Run ID</th>
                <th className="px-5 py-2.5 font-medium">Pipeline / Workflow</th>
                <th className="px-5 py-2.5 font-medium">Status</th>
                <th className="px-5 py-2.5 font-medium">Duration</th>
                <th className="px-5 py-2.5 font-medium">Started</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {runs.data.data.map((r) => (
                <tr key={r.run_id} className="hover:bg-gray-50/50 transition-colors">
                  <td className="px-5 py-3 font-mono text-xs">
                    <Link to={`/runs/${r.run_id}`} className="text-spine-600 hover:text-spine-700 hover:underline">
                      {r.run_id.slice(0, 8)}
                    </Link>
                  </td>
                  <td className="px-5 py-3 text-gray-700 font-medium">{r.pipeline || r.workflow || '—'}</td>
                  <td className="px-5 py-3">
                    <StatusBadge status={r.status} />
                  </td>
                  <td className="px-5 py-3 text-gray-500 font-mono text-xs tabular-nums">
                    {formatDuration(r.duration_ms)}
                  </td>
                  <td className="px-5 py-3 text-gray-400 text-xs">
                    {r.started_at ? formatRelativeTime(r.started_at) : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="px-5 py-8 text-center text-gray-400 text-sm">No runs yet</div>
        )}
      </div>
    </>
  );
}
