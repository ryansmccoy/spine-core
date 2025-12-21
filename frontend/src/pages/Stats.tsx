import PageHeader from '../components/PageHeader';
import { Spinner, ErrorBox } from '../components/UI';
import { useRunStats, useQueueDepths, useWorkers } from '../api/hooks';

const STAT_COLORS: Record<string, string> = {
  pending: 'bg-yellow-100 text-yellow-800',
  running: 'bg-blue-100 text-blue-800',
  completed: 'bg-green-100 text-green-800',
  failed: 'bg-red-100 text-red-800',
  cancelled: 'bg-gray-100 text-gray-800',
  dead_lettered: 'bg-purple-100 text-purple-800',
};

export default function Stats() {
  const stats = useRunStats();
  const queues = useQueueDepths();
  const workers = useWorkers();

  const runStats = stats.data?.data ?? null;
  const queueData = queues.data?.data ?? [];
  const workerData = workers.data?.data ?? [];
  const loading = stats.isLoading || queues.isLoading || workers.isLoading;

  return (
    <>
      <PageHeader
        title="System Stats"
        description="Execution counts, queue depths, and worker status (auto-refreshes every 5s)"
        actions={
          <button
            onClick={() => { stats.refetch(); queues.refetch(); workers.refetch(); }}
            className="px-3 py-1.5 bg-spine-600 text-white text-sm rounded hover:bg-spine-700"
          >
            Refresh
          </button>
        }
      />

      {stats.isError && <ErrorBox message="Failed to load run stats" onRetry={() => stats.refetch()} />}

      {/* Run Stats Grid */}
      <section className="mb-6">
        <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wide mb-3">
          Execution Counts
        </h3>
        {runStats ? (
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
            {(['pending', 'running', 'completed', 'failed', 'cancelled', 'dead_lettered'] as const).map(
              (key) => (
                <div
                  key={key}
                  className={`rounded-lg p-4 text-center ${STAT_COLORS[key]}`}
                >
                  <div className="text-2xl font-bold">{runStats[key]}</div>
                  <div className="text-xs mt-1 capitalize">{key.replace('_', ' ')}</div>
                </div>
              ),
            )}
            <div className="rounded-lg p-4 text-center bg-spine-100 text-spine-900">
              <div className="text-2xl font-bold">{runStats.total}</div>
              <div className="text-xs mt-1">Total</div>
            </div>
          </div>
        ) : (
          <div className="text-gray-400">{loading ? <Spinner /> : 'No data'}</div>
        )}
      </section>

      {/* Queue Depths */}
      <section className="mb-6">
        <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wide mb-3">
          Queue Depths
        </h3>
        {queues.isError && <ErrorBox message="Failed to load queue depths" onRetry={() => queues.refetch()} />}
        {queueData.length > 0 ? (
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-2 text-left">Lane</th>
                  <th className="px-4 py-2 text-left">Pending</th>
                  <th className="px-4 py-2 text-left">Running</th>
                  <th className="px-4 py-2 text-right">Total Active</th>
                </tr>
              </thead>
              <tbody>
                {queueData.map((q) => {
                  const total = q.pending + q.running;
                  const maxDepth = Math.max(...queueData.map((d) => d.pending + d.running), 1);
                  const pendingPct = maxDepth > 0 ? (q.pending / maxDepth) * 100 : 0;
                  const runningPct = maxDepth > 0 ? (q.running / maxDepth) * 100 : 0;
                  return (
                    <tr key={q.lane} className="border-t hover:bg-gray-50">
                      <td className="px-4 py-2 font-mono">{q.lane}</td>
                      <td className="px-4 py-2">
                        <div className="flex items-center gap-2">
                          <div className="w-24 h-2 bg-gray-100 rounded-full overflow-hidden">
                            <div
                              className="h-full bg-yellow-400 rounded-full transition-all"
                              style={{ width: `${pendingPct}%` }}
                            />
                          </div>
                          <span className="text-xs text-yellow-800 font-medium">{q.pending}</span>
                        </div>
                      </td>
                      <td className="px-4 py-2">
                        <div className="flex items-center gap-2">
                          <div className="w-24 h-2 bg-gray-100 rounded-full overflow-hidden">
                            <div
                              className="h-full bg-blue-400 rounded-full transition-all"
                              style={{ width: `${runningPct}%` }}
                            />
                          </div>
                          <span className="text-xs text-blue-800 font-medium">{q.running}</span>
                        </div>
                      </td>
                      <td className="px-4 py-2 text-right font-medium">{total}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-gray-400">{loading ? <Spinner /> : 'All queues empty'}</div>
        )}
      </section>

      {/* Workers */}
      <section>
        <h3 className="text-sm font-medium text-gray-500 uppercase tracking-wide mb-3">
          Workers
        </h3>
        {workers.isError && <ErrorBox message="Failed to load workers" onRetry={() => workers.refetch()} />}
        {workerData.length > 0 ? (
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            {workerData.map((w) => (
              <div key={w.worker_id} className="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
                <div className="flex items-center justify-between mb-2">
                  <code className="text-sm font-bold">{w.worker_id}</code>
                  <span
                    className={`text-xs px-2 py-0.5 rounded ${
                      w.status === 'running'
                        ? 'bg-green-100 text-green-800'
                        : 'bg-gray-100 text-gray-600'
                    }`}
                  >
                    {w.status}
                  </span>
                </div>
                <div className="text-xs text-gray-500 space-y-1">
                  <div>Host: {w.hostname || 'local'}</div>
                  <div>PID: {w.pid}</div>
                  <div>Threads: {w.max_workers}</div>
                  <div>Poll: {w.poll_interval}s</div>
                  <div className="flex gap-4 mt-2">
                    <span className="text-green-700">
                      {w.runs_processed - w.runs_failed} ok
                    </span>
                    <span className="text-red-600">{w.runs_failed} failed</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="bg-yellow-50 border border-yellow-200 rounded p-4 text-sm text-yellow-700">
            No workers connected. Start one with:{' '}
            <code className="bg-yellow-100 px-1 rounded">
              spine-core worker start
            </code>
          </div>
        )}
      </section>
    </>
  );
}
