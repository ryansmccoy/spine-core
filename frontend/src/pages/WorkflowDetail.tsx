import { useParams, useNavigate, Link } from 'react-router-dom';
import PageHeader from '../components/PageHeader';
import StatusBadge from '../components/StatusBadge';
import StepGraph from '../components/StepGraph';
import { Button, Spinner, ErrorBox, EmptyState } from '../components/UI';
import { useWorkflow, useWorkflowRuns, useRunWorkflow } from '../api/hooks';
import { useState } from 'react';
import { Modal } from '../components/UI';
import type { WorkflowDetail as WorkflowDetailType } from '../types/api';

function RunModal({
  workflow,
  onClose,
}: {
  workflow: WorkflowDetailType;
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
        <p className="text-sm text-gray-600">{workflow.description || 'No description'}</p>

        <div>
          <label htmlFor="wfd-params" className="block text-sm font-medium text-gray-700 mb-1">
            Parameters (JSON)
          </label>
          <textarea
            id="wfd-params"
            value={paramsJson}
            onChange={(e) => setParamsJson(e.target.value)}
            rows={4}
            className="w-full border rounded px-3 py-2 text-sm font-mono"
            placeholder='{"key": "value"}'
          />
          {Object.keys(workflow.defaults || {}).length > 0 && (
            <p className="text-xs text-gray-400 mt-1">
              Defaults: {JSON.stringify(workflow.defaults)}
            </p>
          )}
        </div>

        <div className="flex items-center gap-2">
          <input
            type="checkbox"
            id="wfd-dryrun"
            checked={dryRun}
            onChange={(e) => setDryRun(e.target.checked)}
            className="rounded border-gray-300"
          />
          <label htmlFor="wfd-dryrun" className="text-sm text-gray-600">
            Dry run (validate only — no execution queued)
          </label>
        </div>

        {result && (
          <div
            className={`text-sm p-3 rounded ${
              result.startsWith('Error')
                ? 'bg-red-50 text-red-700'
                : 'bg-green-50 text-green-700'
            }`}
          >
            {result}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="secondary" onClick={onClose}>
            Close
          </Button>
          <Button onClick={handleRun} disabled={runWorkflow.isPending}>
            {runWorkflow.isPending ? 'Submitting…' : '▶ Execute'}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

function formatTs(ts: string | null | undefined): string {
  if (!ts) return '—';
  try {
    const d = new Date(ts);
    if (isNaN(d.getTime())) return ts;
    return d.toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' });
  } catch {
    return ts;
  }
}

export default function WorkflowDetailPage() {
  const { name } = useParams<{ name: string }>();
  const nav = useNavigate();
  const workflow = useWorkflow(name ?? '');
  const runs = useWorkflowRuns(name ?? '');
  const [showRun, setShowRun] = useState(false);

  if (workflow.isLoading) return <Spinner />;
  if (workflow.isError) {
    return (
      <ErrorBox
        message={`Workflow '${name}' not found`}
        detail={workflow.error instanceof Error ? workflow.error.message : undefined}
      />
    );
  }

  const w = workflow.data?.data;
  if (!w) return <ErrorBox message="No data" />;

  return (
    <>
      <PageHeader
        title={w.name}
        description={w.description || 'No description'}
        actions={
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => nav('/workflows')}>
              ← Back
            </Button>
            <Button onClick={() => setShowRun(true)}>▶ Run</Button>
          </div>
        }
      />

      {/* Metadata cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-3">
          <p className="text-xs text-gray-500">Domain</p>
          <p className="text-sm font-medium">{w.domain || '—'}</p>
        </div>
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-3">
          <p className="text-xs text-gray-500">Version</p>
          <p className="text-sm font-medium">{w.version}</p>
        </div>
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-3">
          <p className="text-xs text-gray-500">Mode</p>
          <p className="text-sm font-medium capitalize">{w.policy?.mode || 'sequential'}</p>
        </div>
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-3">
          <p className="text-xs text-gray-500">On Failure</p>
          <p className="text-sm font-medium capitalize">{w.policy?.on_failure || 'stop'}</p>
        </div>
      </div>

      {/* Tags */}
      {w.tags && w.tags.length > 0 && (
        <div className="flex gap-2 mb-6">
          {w.tags.map((tag) => (
            <span
              key={tag}
              className="inline-flex items-center px-2 py-0.5 rounded text-xs bg-gray-100 text-gray-600"
            >
              {tag}
            </span>
          ))}
        </div>
      )}

      {/* Step Graph */}
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-5 mb-6">
        <h3 className="text-sm font-medium text-gray-700 mb-3">Step Graph</h3>
        <StepGraph steps={w.steps} />
      </div>

      {/* Steps Table */}
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden mb-6">
        <div className="px-4 py-3 border-b border-gray-100">
          <h3 className="text-sm font-medium text-gray-700">
            Steps ({w.steps.length})
          </h3>
        </div>
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-left text-xs text-gray-500">
            <tr>
              <th className="px-4 py-2">#</th>
              <th className="px-4 py-2">Name</th>
              <th className="px-4 py-2">Pipeline</th>
              <th className="px-4 py-2">Description</th>
              <th className="px-4 py-2">Depends On</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {w.steps.map((step, i) => (
              <tr key={step.name} className="hover:bg-gray-50">
                <td className="px-4 py-2 text-gray-400 text-xs">{i + 1}</td>
                <td className="px-4 py-2 font-medium">{step.name}</td>
                <td className="px-4 py-2 font-mono text-xs text-gray-500">
                  {step.pipeline || '—'}
                </td>
                <td className="px-4 py-2 text-gray-600 text-xs">
                  {step.description || '—'}
                </td>
                <td className="px-4 py-2 text-xs">
                  {step.depends_on && step.depends_on.length > 0 ? (
                    <span className="text-spine-600">{step.depends_on.join(', ')}</span>
                  ) : (
                    <span className="text-gray-400">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Recent Runs */}
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-5">
        <h3 className="text-sm font-medium text-gray-700 mb-3">
          Recent Runs
        </h3>
        {runs.isLoading && <Spinner />}
        {runs.data?.data?.length === 0 && (
          <EmptyState message="No runs yet for this workflow" />
        )}
        {runs.data?.data && runs.data.data.length > 0 && (
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-gray-500 border-b">
              <tr>
                <th className="pb-2">Run ID</th>
                <th className="pb-2">Status</th>
                <th className="pb-2">Started</th>
                <th className="pb-2">Duration</th>
              </tr>
            </thead>
            <tbody>
              {runs.data.data.map((r) => (
                <tr key={r.run_id} className="border-b last:border-0 hover:bg-gray-50">
                  <td className="py-2">
                    <Link
                      to={`/runs/${r.run_id}`}
                      className="font-mono text-xs text-spine-600 hover:underline"
                    >
                      {r.run_id.slice(0, 12)}…
                    </Link>
                  </td>
                  <td className="py-2">
                    <StatusBadge status={r.status} />
                  </td>
                  <td className="py-2 text-gray-500 text-xs">
                    {formatTs(r.started_at)}
                  </td>
                  <td className="py-2 text-gray-500 text-xs font-mono">
                    {r.duration_ms != null
                      ? r.duration_ms < 1000
                        ? `${r.duration_ms.toFixed(0)}ms`
                        : `${(r.duration_ms / 1000).toFixed(1)}s`
                      : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {showRun && (
        <RunModal workflow={w} onClose={() => setShowRun(false)} />
      )}
    </>
  );
}
