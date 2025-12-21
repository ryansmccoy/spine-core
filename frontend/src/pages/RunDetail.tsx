import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import PageHeader from '../components/PageHeader';
import StatusBadge from '../components/StatusBadge';
import EventTimeline from '../components/EventTimeline';
import ConfirmDialog from '../components/ConfirmDialog';
import JsonViewer from '../components/JsonViewer';
import { Button, Spinner, ErrorBox, EmptyState, DetailRow } from '../components/UI';
import { useRun, useRunEvents, useCancelRun, useRetryRun } from '../api/hooks';
import { useToast } from '../components/Toast';

function formatTs(ts: string | null | undefined): string {
  if (!ts) return '—';
  try {
    const d = new Date(ts);
    if (isNaN(d.getTime())) return ts;
    return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'medium' });
  } catch { return ts; }
}

function formatDuration(ms: number | null | undefined): string {
  if (ms == null) return '—';
  if (ms < 1000) return `${ms.toFixed(0)} ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60000).toFixed(1)} min`;
}

type Tab = 'overview' | 'events' | 'params' | 'errors';
const TABS: { key: Tab; label: string }[] = [
  { key: 'overview', label: 'Overview' },
  { key: 'events', label: 'Events' },
  { key: 'params', label: 'Params & Result' },
  { key: 'errors', label: 'Errors' },
];

export default function RunDetail() {
  const { runId } = useParams<{ runId: string }>();
  const nav = useNavigate();
  const run = useRun(runId ?? '');
  const events = useRunEvents(runId ?? '');
  const cancel = useCancelRun();
  const retry = useRetryRun();
  const toast = useToast();
  const [tab, setTab] = useState<Tab>('overview');
  const [confirmAction, setConfirmAction] = useState<'cancel' | 'retry' | null>(null);

  if (run.isLoading) return <Spinner />;
  if (run.isError) return <ErrorBox message="Run not found" detail={run.error instanceof Error ? run.error.message : undefined} />;

  const r = run.data?.data;
  if (!r) return <ErrorBox message="No data" />;

  const isTerminal = ['completed', 'failed', 'cancelled', 'dead_lettered'].includes(r.status);

  const handleConfirm = () => {
    if (confirmAction === 'cancel') {
      cancel.mutate(r.run_id, {
        onSuccess: () => { toast.success(`Run ${r.run_id.slice(0, 8)} cancelled`); setConfirmAction(null); },
        onError: () => { toast.error('Failed to cancel run'); setConfirmAction(null); },
      });
    } else if (confirmAction === 'retry') {
      retry.mutate(r.run_id, {
        onSuccess: () => { toast.success(`Run ${r.run_id.slice(0, 8)} retried`); setConfirmAction(null); },
        onError: () => { toast.error('Failed to retry run'); setConfirmAction(null); },
      });
    }
  };

  return (
    <>
      <PageHeader
        title={`Run ${r.run_id.slice(0, 12)}…`}
        description={r.pipeline || r.workflow || undefined}
        actions={
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => nav('/runs')}>
              ← Back
            </Button>
            {!isTerminal && (
              <Button variant="danger" onClick={() => setConfirmAction('cancel')}>
                Cancel
              </Button>
            )}
            {['failed', 'dead_lettered'].includes(r.status) && (
              <Button onClick={() => setConfirmAction('retry')}>Retry</Button>
            )}
          </div>
        }
      />

      {/* Status bar */}
      <div className="flex items-center gap-4 mb-4 bg-white rounded-lg shadow-sm border border-gray-200 px-5 py-3">
        <StatusBadge status={r.status} />
        <span className="text-sm text-gray-500">{formatDuration(r.duration_ms)}</span>
        <span className="text-xs text-gray-400">{formatTs(r.started_at)} → {formatTs(r.finished_at)}</span>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-4 border-b border-gray-200">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              tab === t.key
                ? 'border-spine-600 text-spine-700'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            {t.label}
            {t.key === 'errors' && r.error && (
              <span className="ml-1.5 inline-flex items-center justify-center w-4 h-4 text-[10px] bg-red-100 text-red-700 rounded-full">!</span>
            )}
            {t.key === 'events' && events.data?.data && (
              <span className="ml-1.5 text-xs text-gray-400">({events.data.data.length})</span>
            )}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {tab === 'overview' && (
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-5">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8">
            <DetailRow label="Run ID" value={<span className="font-mono text-xs select-all">{r.run_id}</span>} />
            <DetailRow label="Status" value={<StatusBadge status={r.status} />} />
            <DetailRow label="Pipeline" value={r.pipeline} />
            <DetailRow label="Workflow" value={r.workflow} />
            <DetailRow label="Started" value={formatTs(r.started_at)} />
            <DetailRow label="Finished" value={formatTs(r.finished_at)} />
            <DetailRow label="Duration" value={formatDuration(r.duration_ms)} />
          </div>
        </div>
      )}

      {tab === 'events' && (
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-5">
          {events.isLoading && <Spinner />}
          {(!events.data?.data || events.data.data.length === 0) && !events.isLoading && (
            <EmptyState message="No events recorded" />
          )}
          {(events.data?.data ?? []).length > 0 && <EventTimeline events={events.data!.data} />}
        </div>
      )}

      {tab === 'params' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-5">
            <h3 className="text-sm font-medium text-gray-700 mb-3">Parameters</h3>
            <JsonViewer data={r.params} />
          </div>
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-5">
            <h3 className="text-sm font-medium text-gray-700 mb-3">Result</h3>
            <JsonViewer data={r.result} />
          </div>
        </div>
      )}

      {tab === 'errors' && (
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-5">
          {r.error ? (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4">
              <h3 className="text-sm font-medium text-red-800 mb-1">Error</h3>
              <pre className="text-xs text-red-700 whitespace-pre-wrap break-words">{r.error}</pre>
            </div>
          ) : (
            <EmptyState message="No errors — run is clean" />
          )}
        </div>
      )}

      {/* Confirm dialog */}
      {confirmAction && (
        <ConfirmDialog
          title={confirmAction === 'cancel' ? 'Cancel Run?' : 'Retry Run?'}
          message={
            confirmAction === 'cancel'
              ? 'This will cancel the running execution. This action cannot be undone.'
              : 'This will retry the failed run with the same parameters.'
          }
          variant={confirmAction === 'cancel' ? 'danger' : 'primary'}
          confirmLabel={confirmAction === 'cancel' ? 'Cancel Run' : 'Retry'}
          onConfirm={handleConfirm}
          onCancel={() => setConfirmAction(null)}
          isPending={cancel.isPending || retry.isPending}
        />
      )}
    </>
  );
}
