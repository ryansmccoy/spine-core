import { useState, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { type ColumnDef } from '@tanstack/react-table';
import { Plus, Filter, XCircle, RotateCw, X } from 'lucide-react';
import PageHeader from '../components/PageHeader';
import StatusBadge from '../components/StatusBadge';
import StatusTabs from '../components/StatusTabs';
import Pagination from '../components/Pagination';
import DataTable from '../components/DataTable';
import { Button, Spinner, ErrorBox, EmptyState, Modal } from '../components/UI';
import { useRuns, useSubmitRun, useCancelRun, useRetryRun, useWorkflows, useRunStats } from '../api/hooks';
import { useToast } from '../components/Toast';
import { formatDuration, formatTimestamp, formatRelativeTime } from '../lib/formatters';
import type { RunSummary, SubmitRunRequest } from '../types/api';

function SubmitDialog({
  onClose,
  onSubmit,
  isPending,
}: {
  onClose: () => void;
  onSubmit: (r: SubmitRunRequest) => void;
  isPending: boolean;
}) {
  const workflows = useWorkflows();
  const workflowNames = workflows.data?.data?.map((w) => w.name) ?? [];
  const [kind, setKind] = useState<'task' | 'pipeline' | 'workflow'>('task');
  const [name, setName] = useState('');
  const [paramsJson, setParamsJson] = useState('{}');
  const [priority, setPriority] = useState('normal');

  return (
    <Modal title="Submit New Run" onClose={onClose}>
      <div className="space-y-3">
        <div>
          <label htmlFor="run-kind" className="block text-sm font-medium text-gray-700 mb-1">Kind</label>
          <select
            id="run-kind"
            value={kind}
            onChange={(e) => { setKind(e.target.value as typeof kind); setName(''); }}
            className="w-full border rounded px-3 py-2 text-sm"
          >
            <option value="task">Task</option>
            <option value="pipeline">Pipeline</option>
            <option value="workflow">Workflow</option>
          </select>
        </div>
        <div>
          <label htmlFor="run-name" className="block text-sm font-medium text-gray-700 mb-1">Name</label>
          {kind === 'workflow' && workflowNames.length > 0 ? (
            <select
              id="run-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full border rounded px-3 py-2 text-sm"
            >
              <option value="">Select a workflow…</option>
              {workflowNames.map((n) => (
                <option key={n} value={n}>{n}</option>
              ))}
            </select>
          ) : (
            <input
              id="run-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={kind === 'workflow' ? 'e.g. etl.daily_ingest' : 'e.g. etl_pipeline'}
              className="w-full border rounded px-3 py-2 text-sm"
            />
          )}
        </div>
        <div>
          <label htmlFor="run-priority" className="block text-sm font-medium text-gray-700 mb-1">Priority</label>
          <select
            id="run-priority"
            value={priority}
            onChange={(e) => setPriority(e.target.value)}
            className="w-full border rounded px-3 py-2 text-sm"
          >
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="normal">Normal</option>
            <option value="low">Low</option>
          </select>
        </div>
        <div>
          <label htmlFor="run-params" className="block text-sm font-medium text-gray-700 mb-1">
            Parameters (JSON)
          </label>
          <textarea
            id="run-params"
            value={paramsJson}
            onChange={(e) => setParamsJson(e.target.value)}
            rows={3}
            className="w-full border rounded px-3 py-2 text-sm font-mono"
            placeholder='{"key": "value"}'
          />
        </div>
      </div>
      <div className="flex justify-end gap-2 mt-5">
        <Button variant="secondary" onClick={onClose}>
          Cancel
        </Button>
        <Button
          disabled={!name || isPending}
          onClick={() => {
            let params: Record<string, unknown> | undefined;
            try {
              const parsed = JSON.parse(paramsJson);
              if (Object.keys(parsed).length > 0) params = parsed;
            } catch { /* ignore */ }
            onSubmit({ kind, name, params, priority });
          }}
        >
          {isPending ? 'Submitting…' : 'Submit'}
        </Button>
      </div>
    </Modal>
  );
}

export default function Runs() {
  const [showDialog, setShowDialog] = useState(false);
  const [statusFilter, setStatusFilter] = useState('');
  const [workflowFilter, setWorkflowFilter] = useState('');
  const [offset, setOffset] = useState(0);
  const [selectedRows, setSelectedRows] = useState<Set<string>>(new Set());
  const limit = 25;
  const runs = useRuns({ status: statusFilter || undefined, pipeline: workflowFilter || undefined, limit, offset });
  const submit = useSubmitRun();
  const cancel = useCancelRun();
  const retry = useRetryRun();
  const workflows = useWorkflows();
  const stats = useRunStats();
  const toast = useToast();
  const workflowNames = workflows.data?.data?.map((w) => w.name) ?? [];

  const pageInfo = runs.data?.page;

  const toggleRow = (runId: string) => {
    setSelectedRows((prev) => {
      const next = new Set(prev);
      if (next.has(runId)) next.delete(runId);
      else next.add(runId);
      return next;
    });
  };

  const toggleAll = () => {
    if (!runs.data?.data) return;
    if (selectedRows.size === runs.data.data.length) {
      setSelectedRows(new Set());
    } else {
      setSelectedRows(new Set(runs.data.data.map((r) => r.run_id)));
    }
  };

  const handleBulkCancel = () => {
    const cancellable = runs.data?.data?.filter(
      (r) => selectedRows.has(r.run_id) && ['pending', 'running'].includes(r.status)
    ) ?? [];
    if (cancellable.length === 0) {
      toast.error('No cancellable runs selected');
      return;
    }
    cancellable.forEach((r) => {
      cancel.mutate(r.run_id, {
        onSuccess: () => toast.success(`Run ${r.run_id.slice(0, 8)} cancelled`),
        onError: () => toast.error(`Failed to cancel ${r.run_id.slice(0, 8)}`),
      });
    });
    setSelectedRows(new Set());
  };

  const handleBulkRetry = () => {
    const retryable = runs.data?.data?.filter(
      (r) => selectedRows.has(r.run_id) && ['failed', 'dead_lettered'].includes(r.status)
    ) ?? [];
    if (retryable.length === 0) {
      toast.error('No retryable runs selected');
      return;
    }
    retryable.forEach((r) => {
      retry.mutate(r.run_id, {
        onSuccess: () => toast.success(`Run ${r.run_id.slice(0, 8)} retried`),
        onError: () => toast.error(`Failed to retry ${r.run_id.slice(0, 8)}`),
      });
    });
    setSelectedRows(new Set());
  };

  const columns = useMemo<ColumnDef<RunSummary, unknown>[]>(() => [
    {
      id: 'select',
      header: () => (
        <input
          type="checkbox"
          className="rounded border-gray-300"
          checked={runs.data?.data ? selectedRows.size === runs.data.data.length && runs.data.data.length > 0 : false}
          onChange={toggleAll}
        />
      ),
      cell: ({ row }) => (
        <input
          type="checkbox"
          className="rounded border-gray-300"
          checked={selectedRows.has(row.original.run_id)}
          onChange={() => toggleRow(row.original.run_id)}
        />
      ),
      enableSorting: false,
      size: 40,
    },
    {
      accessorKey: 'run_id',
      header: 'Run ID',
      cell: ({ row }) => (
        <Link
          to={`/runs/${row.original.run_id}`}
          className="font-mono text-xs text-spine-600 hover:underline"
        >
          {row.original.run_id.slice(0, 12)}…
        </Link>
      ),
      enableSorting: false,
    },
    {
      accessorKey: 'pipeline',
      header: 'Pipeline',
      cell: ({ getValue }) => (getValue() as string) || '—',
    },
    {
      accessorKey: 'workflow',
      header: 'Workflow',
      cell: ({ getValue }) => (
        <span className="text-xs text-gray-500">{(getValue() as string) || '—'}</span>
      ),
    },
    {
      accessorKey: 'status',
      header: 'Status',
      cell: ({ getValue }) => <StatusBadge status={getValue() as string} />,
    },
    {
      accessorKey: 'started_at',
      header: 'Started',
      cell: ({ getValue }) => {
        const ts = getValue() as string | null;
        return (
          <span className="text-gray-500 text-xs" title={formatTimestamp(ts)}>
            {formatRelativeTime(ts)}
          </span>
        );
      },
    },
    {
      accessorKey: 'duration_ms',
      header: 'Duration',
      cell: ({ getValue }) => (
        <span className="text-gray-500 text-xs font-mono">
          {formatDuration(getValue() as number | null)}
        </span>
      ),
    },
    {
      id: 'actions',
      header: '',
      enableSorting: false,
      cell: ({ row }) => {
        const s = row.original.status;
        return (
          <div className="flex gap-1 justify-end">
            {['pending', 'running'].includes(s) && (
              <button
                onClick={() =>
                  cancel.mutate(row.original.run_id, {
                    onSuccess: () => toast.success(`Run ${row.original.run_id.slice(0, 8)} cancelled`),
                    onError: () => toast.error('Failed to cancel run'),
                  })
                }
                className="p-1 text-gray-400 hover:text-red-600 transition-colors rounded"
                title="Cancel"
              >
                <XCircle size={14} />
              </button>
            )}
            {['failed', 'dead_lettered'].includes(s) && (
              <button
                onClick={() =>
                  retry.mutate(row.original.run_id, {
                    onSuccess: () => toast.success(`Run ${row.original.run_id.slice(0, 8)} retried`),
                    onError: () => toast.error('Failed to retry run'),
                  })
                }
                className="p-1 text-gray-400 hover:text-spine-600 transition-colors rounded"
                title="Retry"
              >
                <RotateCw size={14} />
              </button>
            )}
          </div>
        );
      },
    },
  ], [cancel, retry, toast, selectedRows, runs.data?.data]);

  return (
    <>
      <PageHeader
        title="Runs"
        description="View, submit, and manage execution runs"
        actions={
          <Button onClick={() => setShowDialog(true)}>
            <Plus size={14} className="mr-1.5" /> New Run
          </Button>
        }
      />

      {/* Status Tabs + Filters bar */}
      <div className="bg-white rounded-xl border border-gray-200/80 p-3 mb-4">
        <div className="flex flex-wrap gap-3 items-center">
          <StatusTabs
            value={statusFilter}
            onChange={(s) => { setStatusFilter(s); setOffset(0); setSelectedRows(new Set()); }}
            stats={stats.data?.data}
          />

          {workflowNames.length > 0 && (
            <div className="flex items-center gap-1.5">
              <Filter size={14} className="text-gray-400" />
              <select
                value={workflowFilter}
                onChange={(e) => { setWorkflowFilter(e.target.value); setOffset(0); }}
                className="text-xs border border-gray-200 rounded-md px-2.5 py-1.5 bg-white text-gray-700 focus:ring-2 focus:ring-spine-500 focus:border-spine-500"
              >
                <option value="">All Workflows</option>
                {workflowNames.map((n) => (
                  <option key={n} value={n}>{n}</option>
                ))}
              </select>
            </div>
          )}

          {/* Bulk actions */}
          {selectedRows.size > 0 && (
            <div className="flex gap-1.5 ml-auto items-center bg-gray-50 rounded-lg px-3 py-1.5">
              <span className="text-xs font-medium text-gray-600">{selectedRows.size} selected</span>
              <Button variant="danger" size="xs" onClick={handleBulkCancel}>
                <XCircle size={12} className="mr-1" /> Cancel
              </Button>
              <Button variant="secondary" size="xs" onClick={handleBulkRetry}>
                <RotateCw size={12} className="mr-1" /> Retry
              </Button>
              <button
                onClick={() => setSelectedRows(new Set())}
                className="p-1 text-gray-400 hover:text-gray-600 transition-colors"
                title="Clear selection"
              >
                <X size={14} />
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Table */}
      {runs.isLoading && <Spinner />}
      {runs.isError && (
        <ErrorBox 
          message="Failed to load runs" 
          detail={(runs.error as Error)?.message || String(runs.error)}
          onRetry={() => runs.refetch()}
        />
      )}
      {runs.data?.data?.length === 0 && <EmptyState message="No runs found" />}
      {runs.data?.data && runs.data.data.length > 0 && (
        <DataTable
          data={runs.data.data}
          columns={columns}
          searchable
          searchPlaceholder="Filter runs by ID, pipeline, workflow…"
          footer={
            pageInfo ? (
              <Pagination
                total={pageInfo.total}
                limit={pageInfo.limit}
                offset={pageInfo.offset}
                onPageChange={(newOffset) => setOffset(newOffset)}
              />
            ) : undefined
          }
        />
      )}

      {showDialog && (
        <SubmitDialog
          isPending={submit.isPending}
          onClose={() => setShowDialog(false)}
          onSubmit={(r) => {
            submit.mutate(r, {
              onSuccess: () => setShowDialog(false),
            });
          }}
        />
      )}
    </>
  );
}
