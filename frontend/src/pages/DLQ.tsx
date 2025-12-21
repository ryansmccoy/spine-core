import { useState } from 'react';
import PageHeader from '../components/PageHeader';
import { Button, Spinner, ErrorBox, EmptyState } from '../components/UI';
import ConfirmDialog from '../components/ConfirmDialog';
import { useToast } from '../components/Toast';
import { useDLQ, useReplayDLQ } from '../api/hooks';

export default function DLQ() {
  const [pipelineFilter, setPipelineFilter] = useState('');
  const [replayTarget, setReplayTarget] = useState<string | null>(null);
  const [expandedRow, setExpandedRow] = useState<string | null>(null);
  const dlq = useDLQ({ pipeline: pipelineFilter || undefined, limit: 100 });
  const replay = useReplayDLQ();
  const toast = useToast();

  const pipelines = [...new Set((dlq.data?.data ?? []).map((d) => d.pipeline).filter(Boolean))];

  return (
    <>
      <PageHeader
        title="Dead Letter Queue"
        description="Failed items that exceeded retry limits"
      />

      {/* Pipeline filter */}
      {pipelines.length > 1 && (
        <div className="flex gap-2 mb-4">
          <select
            value={pipelineFilter}
            onChange={(e) => setPipelineFilter(e.target.value)}
            className="text-xs border rounded px-2 py-1.5 bg-white"
          >
            <option value="">All Pipelines</option>
            {pipelines.map((p) => (
              <option key={p} value={p!}>{p}</option>
            ))}
          </select>
        </div>
      )}

      {dlq.isLoading && <Spinner />}
      {dlq.isError && <ErrorBox message="Failed to load dead letters" />}
      {dlq.data?.data?.length === 0 && (
        <EmptyState message="Dead letter queue is empty — all clear!" />
      )}

      {dlq.data?.data && dlq.data.data.length > 0 && (
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-left text-xs text-gray-500">
              <tr>
                <th className="px-4 py-3">ID</th>
                <th className="px-4 py-3">Pipeline</th>
                <th className="px-4 py-3">Error</th>
                <th className="px-4 py-3">Created</th>
                <th className="px-4 py-3">Replays</th>
                <th className="px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {dlq.data.data.map((d) => (
                <tr key={d.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-mono text-xs">{d.id.slice(0, 8)}</td>
                  <td className="px-4 py-3">{d.pipeline || '—'}</td>
                  <td className="px-4 py-3 text-red-600 text-xs max-w-md">
                    <button
                      onClick={() => setExpandedRow(expandedRow === d.id ? null : d.id)}
                      className="text-left hover:underline"
                    >
                      {expandedRow === d.id ? d.error : (d.error?.slice(0, 80) + (d.error && d.error.length > 80 ? '…' : ''))}
                    </button>
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-500">
                    {d.created_at || '—'}
                  </td>
                  <td className="px-4 py-3 font-mono">{d.replay_count}</td>
                  <td className="px-4 py-3">
                    <Button
                      size="xs"
                      onClick={() => setReplayTarget(d.id)}
                      disabled={replay.isPending}
                    >
                      Replay
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {replayTarget && (
        <ConfirmDialog
          title="Replay Dead Letter?"
          message="This will re-enqueue the failed item for processing. It will be retried from the beginning."
          variant="primary"
          confirmLabel="Replay"
          onConfirm={() => {
            replay.mutate(replayTarget, {
              onSuccess: () => { setReplayTarget(null); toast.success('Item replayed'); },
              onError: () => { setReplayTarget(null); toast.error('Replay failed'); },
            });
          }}
          onCancel={() => setReplayTarget(null)}
          isPending={replay.isPending}
        />
      )}
    </>
  );
}
