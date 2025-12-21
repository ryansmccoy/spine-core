import { Link } from 'react-router-dom';
import PageHeader from '../components/PageHeader';
import StatusBadge from '../components/StatusBadge';
import { Card, Spinner, ErrorBox } from '../components/UI';
import { useHealth, useCapabilities, useDatabaseHealth, useTableCounts, useRuns, useDLQ } from '../api/hooks';

export default function Dashboard() {
  const health = useHealth();
  const caps = useCapabilities();
  const db = useDatabaseHealth();
  const tables = useTableCounts();
  const runs = useRuns({ limit: 5 });
  const dlq = useDLQ({ limit: 1 });

  if (health.isLoading) return <Spinner />;
  if (health.isError) return <ErrorBox message="Cannot reach spine-core API" />;

  const h = health.data?.data;
  const c = caps.data?.data;
  const d = db.data?.data;

  return (
    <>
      <PageHeader title="Dashboard" description="System health and recent activity" />

      {/* Health row */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
        <Card title="API Status" value={h?.status ?? '—'} color={h?.status === 'healthy' ? 'green' : 'red'} />
        <Card title="Database" value={d?.connected ? 'Connected' : 'Down'} subtitle={d?.backend} color={d?.connected ? 'green' : 'red'} />
        <Card title="Tier" value={c?.tier ?? '—'} color="blue" />
        <Card title="DB Latency" value={d ? `${d.latency_ms.toFixed(1)} ms` : '—'} color="gray" />
        <Card
          title="Dead Letters"
          value={String(dlq.data?.page?.total ?? dlq.data?.data?.length ?? 0)}
          color={(dlq.data?.page?.total ?? 0) > 0 ? 'red' : 'green'}
        />
      </div>

      {/* Capabilities */}
      {c && (
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4 mb-6">
          <h3 className="text-sm font-medium text-gray-700 mb-3">Capabilities</h3>
          <div className="flex flex-wrap gap-2">
            {Object.entries(c).map(([k, v]) =>
              typeof v === 'boolean' ? (
                <StatusBadge
                  key={k}
                  status={v ? k.replace(/_/g, ' ') : `no ${k.replace(/_/g, ' ')}`}
                />
              ) : null,
            )}
          </div>
        </div>
      )}

      {/* Table counts */}
      {tables.data?.data && (
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4 mb-6">
          <h3 className="text-sm font-medium text-gray-700 mb-3">Database Tables</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {(Array.isArray(tables.data.data) ? tables.data.data : []).map((t) => (
              <div key={t.table} className="text-sm">
                <span className="text-gray-500">{t.table}</span>{' '}
                <span className="font-mono font-medium">{t.count}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recent runs */}
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
        <h3 className="text-sm font-medium text-gray-700 mb-3">Recent Runs</h3>
        {runs.data?.data?.length ? (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-gray-500 border-b">
                <th className="pb-2">ID</th>
                <th className="pb-2">Pipeline</th>
                <th className="pb-2">Status</th>
                <th className="pb-2">Started</th>
              </tr>
            </thead>
            <tbody>
              {runs.data.data.map((r) => (
                <tr key={r.run_id} className="border-b last:border-0 hover:bg-gray-50">
                  <td className="py-2 font-mono text-xs">
                    <Link to={`/runs/${r.run_id}`} className="text-spine-600 hover:underline">
                      {r.run_id.slice(0, 8)}
                    </Link>
                  </td>
                  <td className="py-2">{r.pipeline || '—'}</td>
                  <td className="py-2">
                    <StatusBadge status={r.status} />
                  </td>
                  <td className="py-2 text-gray-500">{r.started_at ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="text-gray-400 text-sm">No runs yet</p>
        )}
      </div>
    </>
  );
}
