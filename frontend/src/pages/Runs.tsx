import { useState, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { type ColumnDef } from '@tanstack/react-table';
import PageHeader from '../components/PageHeader';
import StatusBadge from '../components/StatusBadge';
import Pagination from '../components/Pagination';
import DataTable from '../components/DataTable';
import { Button, Spinner, ErrorBox, EmptyState, Modal } from '../components/UI';
import { useRuns, useSubmitRun, useCancelRun, useWorkflows } from '../api/hooks';
import { useToast } from '../components/Toast';
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
  const limit = 25;
  const runs = useRuns({ status: statusFilter || undefined, pipeline: workflowFilter || undefined, limit, offset });
  const submit = useSubmitRun();
  const cancel = useCancelRun();
  const workflows = useWorkflows();
  const toast = useToast();
  const workflowNames = workflows.data?.data?.map((w) => w.name) ?? [];

  const formatTs = (ts: string | null | undefined) => {
    if (!ts) return '—';
    try {
      const d = new Date(ts);
      if (isNaN(d.getTime())) return ts;
      return d.toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' });
    } catch { return ts; }
  };

  const pageInfo = runs.data?.page;

  const columns = useMemo<ColumnDef<RunSummary, unknown>[]>(() => [
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
      cell: ({ getValue }) => (
        <span className="text-gray-500 text-xs">{formatTs(getValue() as string | null)}</span>
      ),
    },
    {
      accessorKey: 'finished_at',
      header: 'Finished',
      cell: ({ getValue }) => (
        <span className="text-gray-500 text-xs">{formatTs(getValue() as string | null)}</span>
      ),
    },
    {
      accessorKey: 'duration_ms',
      header: 'Duration',
      cell: ({ getValue }) => {
        const v = getValue() as number | null;
        return (
          <span className="text-gray-500 text-xs font-mono">
            {v != null ? (v < 1000 ? `${v.toFixed(0)}ms` : `${(v / 1000).toFixed(1)}s`) : '—'}
          </span>
        );
      },
    },
    {
      id: 'actions',
      header: 'Actions',
      enableSorting: false,
      cell: ({ row }) =>
        ['pending', 'running'].includes(row.original.status) ? (
          <Button
            variant="danger"
            size="xs"
            onClick={() =>
              cancel.mutate(row.original.run_id, {
                onSuccess: () => toast.success(`Run ${row.original.run_id.slice(0, 8)} cancelled`),
                onError: () => toast.error('Failed to cancel run'),
              })
            }
          >
            Cancel
          </Button>
        ) : null,
    },
  ], [cancel, toast, formatTs]);

  return (
    <>
      <PageHeader
        title="Execution Runs"
        description="View, submit, and manage run executions"
        actions={
          <Button onClick={() => setShowDialog(true)}>+ Submit Run</Button>
        }
      />

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-4 items-center">
        <div className="flex gap-1">
          {['', 'pending', 'running', 'completed', 'failed', 'cancelled'].map(
            (s) => (
              <button
                key={s}
                onClick={() => { setStatusFilter(s); setOffset(0); }}
                className={`text-xs px-3 py-1.5 rounded-full transition-colors ${
                  statusFilter === s
                    ? 'bg-spine-600 text-white'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                {s || 'All'}
              </button>
            ),
          )}
        </div>
        {workflowNames.length > 0 && (
          <select
            value={workflowFilter}
            onChange={(e) => { setWorkflowFilter(e.target.value); setOffset(0); }}
            className="text-xs border rounded px-2 py-1.5 bg-white"
          >
            <option value="">All Workflows</option>
            {workflowNames.map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        )}
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
