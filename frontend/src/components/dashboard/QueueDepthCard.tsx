/**
 * Queue depth visualization showing pending/running counts per priority lane.
 */

interface QueueDepth {
  lane: string;
  pending: number;
  running: number;
}

interface QueueDepthCardProps {
  queues: QueueDepth[];
}

const LANE_ORDER = ['realtime', 'critical', 'high', 'normal', 'low'];

export default function QueueDepthCard({ queues }: QueueDepthCardProps) {
  const sorted = [...queues].sort(
    (a, b) => (LANE_ORDER.indexOf(a.lane) ?? 99) - (LANE_ORDER.indexOf(b.lane) ?? 99),
  );

  const maxTotal = Math.max(...sorted.map((q) => q.pending + q.running), 1);

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
      <h3 className="text-sm font-medium text-gray-700 mb-3">Queue Depth</h3>
      {sorted.length === 0 ? (
        <p className="text-sm text-gray-400">No queues active</p>
      ) : (
        <div className="space-y-2">
          {sorted.map((q) => {
            const total = q.pending + q.running;
            const pct = (total / maxTotal) * 100;
            const runPct = total > 0 ? (q.running / total) * pct : 0;
            const pendPct = pct - runPct;
            return (
              <div key={q.lane}>
                <div className="flex items-center justify-between mb-0.5">
                  <span className="text-xs font-medium text-gray-600 capitalize">{q.lane}</span>
                  <span className="text-xs text-gray-400">
                    {q.pending} pending, {q.running} running
                  </span>
                </div>
                <div className="h-2 bg-gray-100 rounded-full overflow-hidden flex">
                  <div
                    className="bg-blue-500 transition-all duration-500"
                    style={{ width: `${runPct}%` }}
                  />
                  <div
                    className="bg-yellow-400 transition-all duration-500"
                    style={{ width: `${pendPct}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
