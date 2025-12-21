import { useParams, useNavigate, Link } from 'react-router-dom';
import { ArrowLeft, Play, Globe, Layers, GitFork, AlertTriangle } from 'lucide-react';
import StatusBadge from '../components/StatusBadge';
import { WorkflowDAG } from '../components/dag';
import { Button, Spinner, ErrorBox, EmptyState } from '../components/UI';
import { useWorkflow, useWorkflowRuns, useRunWorkflow } from '../api/hooks';
import { formatDuration, formatTimestamp } from '../lib/formatters';
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
            <Play className="w-3.5 h-3.5 mr-1" />{runWorkflow.isPending ? 'Submitting…' : 'Execute'}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

/* formatTs and formatDuration imported from lib/formatters */

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
      {/* Custom header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <button onClick={() => nav('/workflows')} className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors">
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div>
            <h1 className="text-xl font-bold text-gray-900 tracking-tight">{w.name}</h1>
            <p className="text-sm text-gray-500 mt-0.5">{w.description || 'No description'}</p>
          </div>
        </div>
        <Button onClick={() => setShowRun(true)}>
          <Play className="w-3.5 h-3.5 mr-1.5" />Run
        </Button>
      </div>

      {/* Metadata cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <div className="bg-white rounded-xl shadow-sm border border-gray-200/80 p-3">
          <p className="text-xs font-medium text-gray-400 uppercase tracking-wider flex items-center gap-1"><Globe className="w-3 h-3" />Domain</p>
          <p className="text-sm font-medium mt-1">{w.domain || '—'}</p>
        </div>
        <div className="bg-white rounded-xl shadow-sm border border-gray-200/80 p-3">
          <p className="text-xs font-medium text-gray-400 uppercase tracking-wider">Version</p>
          <p className="text-sm font-medium mt-1">{w.version}</p>
        </div>
        <div className="bg-white rounded-xl shadow-sm border border-gray-200/80 p-3">
          <p className="text-xs font-medium text-gray-400 uppercase tracking-wider flex items-center gap-1"><Layers className="w-3 h-3" />Mode</p>
          <p className="text-sm font-medium capitalize mt-1">{w.policy?.mode || 'sequential'}</p>
        </div>
        <div className="bg-white rounded-xl shadow-sm border border-gray-200/80 p-3">
          <p className="text-xs font-medium text-gray-400 uppercase tracking-wider flex items-center gap-1"><AlertTriangle className="w-3 h-3" />On Failure</p>
          <p className="text-sm font-medium capitalize mt-1">{w.policy?.on_failure || 'stop'}</p>
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

      {/* Workflow DAG */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200/80 p-5 mb-6">
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3 flex items-center gap-1.5">
          <GitFork className="w-3.5 h-3.5" />Step Graph
        </h3>
        <WorkflowDAG steps={w.steps} height={320} showMinimap={w.steps.length >= 8} />
      </div>

      {/* Steps Table */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200/80 overflow-hidden mb-6">
        <div className="px-5 py-3 border-b border-gray-100">
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
            Steps ({w.steps.length})
          </h3>
        </div>
        <table className="w-full text-sm">
          <thead className="bg-gray-50/80 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
            <tr>
              <th className="px-5 py-2.5">#</th>
              <th className="px-5 py-2.5">Name</th>
              <th className="px-5 py-2.5">Pipeline</th>
              <th className="px-5 py-2.5">Description</th>
              <th className="px-5 py-2.5">Depends On</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100/80">
            {w.steps.map((step, i) => (
              <tr key={step.name} className="hover:bg-gray-50/50">
                <td className="px-5 py-2.5 text-gray-400 text-xs">{i + 1}</td>
                <td className="px-5 py-2.5 font-medium">{step.name}</td>
                <td className="px-5 py-2.5 font-mono text-xs text-gray-500">
                  {step.pipeline || '—'}
                </td>
                <td className="px-5 py-2.5 text-gray-600 text-xs">
                  {step.description || '—'}
                </td>
                <td className="px-5 py-2.5 text-xs">
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
      <div className="bg-white rounded-xl shadow-sm border border-gray-200/80 p-5">
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
          Recent Runs
        </h3>
        {runs.isLoading && <Spinner />}
        {runs.data?.data?.length === 0 && (
          <EmptyState message="No runs yet for this workflow" />
        )}
        {runs.data?.data && runs.data.data.length > 0 && (
          <table className="w-full text-sm">
            <thead className="text-left text-xs font-medium text-gray-500 uppercase tracking-wider border-b">
              <tr>
                <th className="pb-2.5">Run ID</th>
                <th className="pb-2.5">Status</th>
                <th className="pb-2.5">Started</th>
                <th className="pb-2.5">Duration</th>
              </tr>
            </thead>
            <tbody>
              {runs.data.data.map((r) => (
                <tr key={r.run_id} className="border-b last:border-0 hover:bg-gray-50/50">
                  <td className="py-2.5">
                    <Link
                      to={`/runs/${r.run_id}`}
                      className="font-mono text-xs text-spine-600 hover:underline"
                    >
                      {r.run_id.slice(0, 12)}…
                    </Link>
                  </td>
                  <td className="py-2.5">
                    <StatusBadge status={r.status} />
                  </td>
                  <td className="py-2.5 text-gray-500 text-xs">
                    {formatTimestamp(r.started_at)}
                  </td>
                  <td className="py-2.5 text-gray-500 text-xs font-mono">
                    {formatDuration(r.duration_ms)}
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
