import { useState } from 'react';
import PageHeader from '../components/PageHeader';
import { Button, Spinner, ErrorBox, EmptyState, Modal } from '../components/UI';
import ConfirmDialog from '../components/ConfirmDialog';
import { useToast } from '../components/Toast';
import {
  useSchedules,
  useCreateSchedule,
  useDeleteSchedule,
  useUpdateSchedule,
  useWorkflows,
} from '../api/hooks';
import type { CreateScheduleRequest, UpdateScheduleRequest, ScheduleSummary } from '../types/api';

function CreateDialog({
  onClose,
  onSubmit,
  isPending,
}: {
  onClose: () => void;
  onSubmit: (r: CreateScheduleRequest) => void;
  isPending: boolean;
}) {
  const workflows = useWorkflows();
  const workflowNames = workflows.data?.data?.map((w) => w.name) ?? [];
  const [workflowName, setWorkflowName] = useState('');
  const [cron, setCron] = useState('');
  const [interval, setInterval] = useState('');
  const [paramsJson, setParamsJson] = useState('{}');

  return (
    <Modal title="Create Schedule" onClose={onClose}>
      <div className="space-y-3">
        <div>
          <label htmlFor="sched-workflow" className="block text-sm font-medium text-gray-700 mb-1">
            Workflow
          </label>
          {workflowNames.length > 0 ? (
            <select
              id="sched-workflow"
              value={workflowName}
              onChange={(e) => setWorkflowName(e.target.value)}
              className="w-full border rounded px-3 py-2 text-sm"
            >
              <option value="">Select a workflow…</option>
              {workflowNames.map((n) => (
                <option key={n} value={n}>{n}</option>
              ))}
            </select>
          ) : (
            <input
              id="sched-workflow"
              value={workflowName}
              onChange={(e) => setWorkflowName(e.target.value)}
              placeholder="e.g. etl.daily_ingest"
              className="w-full border rounded px-3 py-2 text-sm"
            />
          )}
        </div>
        <div>
          <label htmlFor="sched-cron" className="block text-sm font-medium text-gray-700 mb-1">
            Cron Expression
          </label>
          <input
            id="sched-cron"
            value={cron}
            onChange={(e) => setCron(e.target.value)}
            placeholder="e.g. 0 * * * * (every hour)"
            className="w-full border rounded px-3 py-2 text-sm font-mono"
          />
          <p className="text-xs text-gray-400 mt-1">Standard cron syntax: min hour day month weekday</p>
        </div>
        <div>
          <label htmlFor="sched-interval" className="block text-sm font-medium text-gray-700 mb-1">
            OR Interval (seconds)
          </label>
          <input
            id="sched-interval"
            value={interval}
            onChange={(e) => setInterval(e.target.value)}
            placeholder="e.g. 3600"
            type="number"
            className="w-full border rounded px-3 py-2 text-sm font-mono"
          />
        </div>
        <div>
          <label htmlFor="sched-params" className="block text-sm font-medium text-gray-700 mb-1">
            Parameters (JSON)
          </label>
          <textarea
            id="sched-params"
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
          disabled={!workflowName || isPending}
          onClick={() => {
            let params: Record<string, unknown> | undefined;
            try {
              const parsed = JSON.parse(paramsJson);
              if (Object.keys(parsed).length > 0) params = parsed;
            } catch { /* ignore bad JSON, send without params */ }
            onSubmit({
              workflow_name: workflowName,
              cron: cron || undefined,
              interval_seconds: interval ? Number(interval) : undefined,
              params,
            });
          }}
        >
          {isPending ? 'Creating…' : 'Create'}
        </Button>
      </div>
    </Modal>
  );
}

function EditDialog({
  schedule,
  onClose,
  onSubmit,
  isPending,
}: {
  schedule: ScheduleSummary;
  onClose: () => void;
  onSubmit: (body: UpdateScheduleRequest) => void;
  isPending: boolean;
}) {
  const [cron, setCron] = useState(schedule.cron || '');
  const [interval, setInterval] = useState(
    schedule.interval_seconds ? String(schedule.interval_seconds) : '',
  );
  const [enabled, setEnabled] = useState(schedule.enabled);

  return (
    <Modal title={`Edit Schedule ${schedule.schedule_id.slice(0, 8)}`} onClose={onClose}>
      <div className="space-y-3">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Workflow
          </label>
          <input
            value={schedule.workflow_name}
            disabled
            className="w-full border rounded px-3 py-2 text-sm bg-gray-50 text-gray-500"
          />
          <p className="text-xs text-gray-400 mt-1">Workflow cannot be changed — delete and recreate instead.</p>
        </div>
        <div>
          <label htmlFor="edit-cron" className="block text-sm font-medium text-gray-700 mb-1">
            Cron Expression
          </label>
          <input
            id="edit-cron"
            value={cron}
            onChange={(e) => setCron(e.target.value)}
            placeholder="e.g. 0 * * * * (every hour)"
            className="w-full border rounded px-3 py-2 text-sm font-mono"
          />
          <p className="text-xs text-gray-400 mt-1">Standard cron syntax: min hour day month weekday</p>
        </div>
        <div>
          <label htmlFor="edit-interval" className="block text-sm font-medium text-gray-700 mb-1">
            OR Interval (seconds)
          </label>
          <input
            id="edit-interval"
            value={interval}
            onChange={(e) => setInterval(e.target.value)}
            placeholder="e.g. 3600"
            type="number"
            className="w-full border rounded px-3 py-2 text-sm font-mono"
          />
        </div>
        <div className="flex items-center gap-2">
          <input
            id="edit-enabled"
            type="checkbox"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
            className="rounded border-gray-300"
          />
          <label htmlFor="edit-enabled" className="text-sm text-gray-700">
            Enabled
          </label>
        </div>
      </div>
      <div className="flex justify-end gap-2 mt-5">
        <Button variant="secondary" onClick={onClose}>
          Cancel
        </Button>
        <Button
          disabled={isPending}
          onClick={() => {
            const body: UpdateScheduleRequest = { enabled };
            if (cron) body.cron = cron;
            if (interval) body.interval_seconds = Number(interval);
            onSubmit(body);
          }}
        >
          {isPending ? 'Saving…' : 'Save Changes'}
        </Button>
      </div>
    </Modal>
  );
}

export default function Schedules() {
  const [showCreate, setShowCreate] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [editTarget, setEditTarget] = useState<ScheduleSummary | null>(null);
  const schedules = useSchedules();
  const create = useCreateSchedule();
  const del = useDeleteSchedule();
  const update = useUpdateSchedule();
  const toast = useToast();

  /** Human-readable cron description */
  const describeCron = (cron: string | null | undefined, intervalSec: number | null | undefined) => {
    if (cron) {
      const parts = cron.split(' ');
      if (cron === '* * * * *') return 'Every minute';
      if (parts[0] === '0' && parts[1] === '*') return 'Every hour';
      if (parts[0] === '0' && parts[1] === '0') return 'Daily at midnight';
      return cron;
    }
    if (intervalSec) {
      if (intervalSec < 60) return `Every ${intervalSec}s`;
      if (intervalSec < 3600) return `Every ${(intervalSec / 60).toFixed(0)} min`;
      return `Every ${(intervalSec / 3600).toFixed(1)} hr`;
    }
    return '—';
  };

  return (
    <>
      <PageHeader
        title="Schedules"
        description="Manage recurring workflow executions"
        actions={
          <Button onClick={() => setShowCreate(true)}>+ New Schedule</Button>
        }
      />

      {schedules.isLoading && <Spinner />}
      {schedules.isError && (
        <ErrorBox
          message="Failed to load schedules"
          detail={schedules.error instanceof Error ? schedules.error.message : undefined}
          onRetry={() => schedules.refetch()}
        />
      )}
      {schedules.data?.data?.length === 0 && (
        <EmptyState message="No schedules configured" />
      )}

      {schedules.data?.data && schedules.data.data.length > 0 && (
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-left text-xs text-gray-500">
              <tr>
                <th className="px-4 py-3">ID</th>
                <th className="px-4 py-3">Workflow</th>
                <th className="px-4 py-3">Schedule</th>
                <th className="px-4 py-3">Enabled</th>
                <th className="px-4 py-3">Next Run</th>
                <th className="px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {schedules.data.data.map((s) => (
                <tr key={s.schedule_id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-mono text-xs">
                    {s.schedule_id.slice(0, 8)}
                  </td>
                  <td className="px-4 py-3">{s.workflow_name}</td>
                  <td className="px-4 py-3 font-mono text-xs" title={s.cron || `${s.interval_seconds}s`}>
                    {describeCron(s.cron, s.interval_seconds)}
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() =>
                        update.mutate({
                          id: s.schedule_id,
                          body: { enabled: !s.enabled },
                        })
                      }
                      className={`text-xs px-2 py-0.5 rounded ${
                        s.enabled
                          ? 'bg-green-100 text-green-700'
                          : 'bg-gray-100 text-gray-500'
                      }`}
                    >
                      {s.enabled ? 'On' : 'Off'}
                    </button>
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-500">
                    {s.next_run || '—'}
                  </td>
                  <td className="px-4 py-3 flex gap-1">
                    <Button
                      variant="secondary"
                      size="xs"
                      onClick={() => setEditTarget(s)}
                    >
                      Edit
                    </Button>
                    <Button
                      variant="danger"
                      size="xs"
                      onClick={() => setDeleteTarget(s.schedule_id)}
                    >
                      Delete
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showCreate && (
        <CreateDialog
          isPending={create.isPending}
          onClose={() => setShowCreate(false)}
          onSubmit={(r) => {
            create.mutate(r, {
              onSuccess: () => { setShowCreate(false); toast.success('Schedule created'); },
              onError: () => toast.error('Failed to create schedule'),
            });
          }}
        />
      )}

      {deleteTarget && (
        <ConfirmDialog
          title="Delete Schedule?"
          message="This will permanently remove the schedule. Any pending executions will not be affected."
          variant="danger"
          confirmLabel="Delete"
          onConfirm={() => {
            del.mutate(deleteTarget, {
              onSuccess: () => { setDeleteTarget(null); toast.success('Schedule deleted'); },
              onError: () => { setDeleteTarget(null); toast.error('Failed to delete schedule'); },
            });
          }}
          onCancel={() => setDeleteTarget(null)}
          isPending={del.isPending}
        />
      )}

      {editTarget && (
        <EditDialog
          schedule={editTarget}
          isPending={update.isPending}
          onClose={() => setEditTarget(null)}
          onSubmit={(body) => {
            update.mutate(
              { id: editTarget.schedule_id, body },
              {
                onSuccess: () => { setEditTarget(null); toast.success('Schedule updated'); },
                onError: () => toast.error('Failed to update schedule'),
              },
            );
          }}
        />
      )}
    </>
  );
}
