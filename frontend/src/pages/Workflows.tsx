import { useState } from 'react';
import { Link } from 'react-router-dom';
import PageHeader from '../components/PageHeader';
import { Button, Spinner, ErrorBox, EmptyState, Modal } from '../components/UI';
import StatusBadge from '../components/StatusBadge';
import { useWorkflows, useRunWorkflow } from '../api/hooks';
import type { WorkflowSummary } from '../types/api';

function RunWorkflowModal({
  workflow,
  onClose,
}: {
  workflow: WorkflowSummary;
  onClose: () => void;
}) {
  const runWorkflow = useRunWorkflow();
  const [paramsJson, setParamsJson] = useState('{}');
  const [dryRun, setDryRun] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  const handleRun = () => {
    let params: Record<string, unknown> = {};
    try {
      params = JSON.parse(paramsJson);
    } catch {
      setResult('Invalid JSON in parameters');
      return;
    }
    runWorkflow.mutate(
      { name: workflow.name, body: { params, dry_run: dryRun } },
      {
        onSuccess: (data) => {
          setResult(`Run submitted: ${data?.data?.run_id ?? 'OK'}${dryRun ? ' (dry run)' : ''}`);
        },
        onError: (err) => {
          setResult(`Error: ${err instanceof Error ? err.message : String(err)}`);
        },
      },
    );
  };

  return (
    <Modal title={`Run: ${workflow.name}`} onClose={onClose}>
      <div className="space-y-4">
        <div>
          <p className="text-sm text-gray-600">{workflow.description || 'No description'}</p>
          <p className="text-xs text-gray-400 mt-1">{workflow.step_count} step{workflow.step_count !== 1 ? 's' : ''}</p>
        </div>

        <div>
          <label htmlFor="wf-params" className="block text-sm font-medium text-gray-700 mb-1">
            Parameters (JSON)
          </label>
          <textarea
            id="wf-params"
            value={paramsJson}
            onChange={(e) => setParamsJson(e.target.value)}
            rows={4}
            className="w-full border rounded px-3 py-2 text-sm font-mono"
            placeholder='{"key": "value"}'
          />
        </div>

        <div className="flex items-center gap-2">
          <input
            type="checkbox"
            id="wf-dryrun"
            checked={dryRun}
            onChange={(e) => setDryRun(e.target.checked)}
            className="rounded border-gray-300"
          />
          <label htmlFor="wf-dryrun" className="text-sm text-gray-600">Dry run (validate only)</label>
        </div>

        {result && (
          <div className={`text-sm p-3 rounded ${result.startsWith('Error') ? 'bg-red-50 text-red-700' : 'bg-green-50 text-green-700'}`}>
            {result}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="secondary" onClick={onClose}>Close</Button>
          <Button onClick={handleRun} disabled={runWorkflow.isPending}>
            {runWorkflow.isPending ? 'Submitting…' : '▶ Execute'}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

export default function Workflows() {
  const workflows = useWorkflows();
  const [selectedWorkflow, setSelectedWorkflow] = useState<WorkflowSummary | null>(null);

  return (
    <>
      <PageHeader
        title="Workflows"
        description="Registered workflow definitions — trigger executions"
      />

      {workflows.isLoading && <Spinner />}
      {workflows.isError && (
        <ErrorBox
          message="Failed to load workflows"
          detail={workflows.error instanceof Error ? workflows.error.message : undefined}
          onRetry={() => workflows.refetch()}
        />
      )}
      {workflows.data?.data?.length === 0 && (
        <EmptyState message="No workflows registered" />
      )}

      {workflows.data?.data && workflows.data.data.length > 0 && (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {workflows.data.data.map((w) => (
            <div
              key={w.name}
              className="bg-white rounded-lg shadow-sm border border-gray-200 p-5 hover:shadow-md transition-shadow"
            >
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="font-semibold text-gray-900">{w.name}</h3>
                  <p className="text-sm text-gray-500 mt-1">{w.description || 'No description'}</p>
                </div>
                <StatusBadge status={`${w.step_count} steps`} />
              </div>
              <div className="flex items-center justify-between mt-4 pt-3 border-t border-gray-100 gap-2">
                <Link
                  to={`/workflows/${encodeURIComponent(w.name)}`}
                  className="text-xs text-spine-600 hover:underline font-medium"
                >
                  View Details →
                </Link>
                <Button size="xs" onClick={() => setSelectedWorkflow(w)}>
                  ▶ Run
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      {selectedWorkflow && (
        <RunWorkflowModal
          workflow={selectedWorkflow}
          onClose={() => setSelectedWorkflow(null)}
        />
      )}
    </>
  );
}
