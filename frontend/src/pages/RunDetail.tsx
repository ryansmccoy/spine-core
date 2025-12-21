import { useState, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  Ban,
  RotateCw,
  Clock,
  Timer,
  Hash,
  GitBranch,
  Activity,
  FileText,
  Code2,
  AlertTriangle,
  Layers,
} from 'lucide-react';
import StatusBadge from '../components/StatusBadge';
import EventTimeline from '../components/EventTimeline';
import ConfirmDialog from '../components/ConfirmDialog';
import JsonViewer from '../components/JsonViewer';
import SplitPanel from '../components/SplitPanel';
import { WorkflowDAG } from '../components/dag';
import { StepGanttChart } from '../components/charts';
import StepDetailDrawer from '../components/run/StepDetailDrawer';
import LogViewer from '../components/run/LogViewer';
import { Button, Spinner, ErrorBox, EmptyState } from '../components/UI';
import { useRun, useRunEvents, useRunSteps, useRunLogs, useWorkflow, useCancelRun, useRetryRun } from '../api/hooks';
import { useToast } from '../components/Toast';
import { formatDuration, formatTimestamp } from '../lib/formatters';
import { getStatusStyle } from '../lib/colors';
import type { StepState } from '../components/dag/dagre-layout';
import type { WorkflowStep } from '../types/api';

type Tab = 'overview' | 'graph' | 'events' | 'params' | 'errors' | 'logs';

const TABS: { key: Tab; label: string; icon: React.ElementType }[] = [
  { key: 'overview', label: 'Overview', icon: Activity },
  { key: 'graph', label: 'Graph', icon: GitBranch },
  { key: 'events', label: 'Timeline', icon: Layers },
  { key: 'logs', label: 'Logs', icon: FileText },
  { key: 'params', label: 'Parameters', icon: Code2 },
  { key: 'errors', label: 'Errors', icon: AlertTriangle },
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
  const [selectedStep, setSelectedStep] = useState<WorkflowStep | null>(null);

  const r = run.data?.data;

  // Fetch workflow definition for DAG structure (only if run has a workflow)
  const workflowName = r?.workflow ?? '';
  const workflow = useWorkflow(workflowName);

  // Fetch step-level timing
  const isActive = r ? !['completed', 'failed', 'cancelled', 'dead_lettered'].includes(r.status) : false;
  const steps = useRunSteps(runId ?? '', { enabled: !!workflowName });
  const logs = useRunLogs(runId ?? '');

  // Build stepStates map for DAG overlay
  const stepStates = useMemo<Record<string, StepState>>(() => {
    const map: Record<string, StepState> = {};
    for (const s of steps.data?.data ?? []) {
      map[s.step_name] = {
        status: s.status,
        startedAt: s.started_at ?? undefined,
        finishedAt: s.completed_at ?? undefined,
        durationMs: s.duration_ms ?? undefined,
        error: s.error ?? undefined,
      };
    }
    return map;
  }, [steps.data]);

  if (run.isLoading) return <Spinner />;
  if (run.isError) return <ErrorBox message="Run not found" detail={run.error instanceof Error ? run.error.message : undefined} />;
  if (!r) return <ErrorBox message="No data" />;

  const isTerminal = ['completed', 'failed', 'cancelled', 'dead_lettered'].includes(r.status);
  const wSteps = workflow.data?.data?.steps ?? [];
  const hasWorkflow = !!workflowName && wSteps.length > 0;

  const selectedStepState = selectedStep ? stepStates[selectedStep.name] : undefined;

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
      {/* Top bar with back nav + actions */}
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-3">
          <button
            onClick={() => nav('/runs')}
            className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-semibold text-gray-900 tracking-tight">
                Run <span className="font-mono">{r.run_id.slice(0, 8)}</span>
              </h1>
              <StatusBadge status={r.status} />
            </div>
            {(r.pipeline || r.workflow) && (
              <p className="text-sm text-gray-500 mt-0.5">{r.pipeline || r.workflow}</p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {!isTerminal && (
            <Button variant="danger" onClick={() => setConfirmAction('cancel')}>
              <Ban className="w-3.5 h-3.5 mr-1.5" />Cancel
            </Button>
          )}
          {['failed', 'dead_lettered'].includes(r.status) && (
            <Button onClick={() => setConfirmAction('retry')}>
              <RotateCw className="w-3.5 h-3.5 mr-1.5" />Retry
            </Button>
          )}
        </div>
      </div>

      {/* Status bar */}
      <div className="flex items-center gap-5 mb-5 bg-white rounded-xl shadow-sm border border-gray-200/80 px-5 py-3">
        <div className="flex items-center gap-2 text-sm text-gray-600">
          <Hash className="w-3.5 h-3.5 text-gray-400" />
          <span className="font-mono text-xs select-all">{r.run_id.slice(0, 12)}</span>
        </div>
        <div className="w-px h-4 bg-gray-200" />
        <div className="flex items-center gap-2 text-sm text-gray-600">
          <Timer className="w-3.5 h-3.5 text-gray-400" />
          <span className="font-mono">{formatDuration(r.duration_ms)}</span>
        </div>
        <div className="w-px h-4 bg-gray-200" />
        <div className="flex items-center gap-2 text-sm text-gray-500">
          <Clock className="w-3.5 h-3.5 text-gray-400" />
          <span className="text-xs">{formatTimestamp(r.started_at)} → {formatTimestamp(r.finished_at)}</span>
        </div>
        {isActive && (
          <span className="ml-auto flex items-center gap-1.5 text-xs font-medium text-blue-600">
            <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
            Live
          </span>
        )}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-5 border-b border-gray-200">
        {TABS.filter(t => t.key !== 'graph' || hasWorkflow).map((t) => {
          const Icon = t.icon;
          const isSelected = tab === t.key;
          return (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                isSelected
                  ? 'border-spine-600 text-spine-700'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              <Icon className={`w-3.5 h-3.5 ${isSelected ? 'text-spine-600' : 'text-gray-400'}`} />
              {t.label}
              {t.key === 'errors' && r.error && (
                <span className="inline-flex items-center justify-center w-4 h-4 text-[10px] bg-red-100 text-red-700 rounded-full font-bold">!</span>
              )}
              {t.key === 'events' && events.data?.data && (
                <span className="text-xs text-gray-400">({events.data.data.length})</span>
              )}
              {t.key === 'graph' && steps.data?.data && (
                <span className="text-xs text-gray-400">({steps.data.data.length})</span>
              )}
              {t.key === 'logs' && logs.data?.data && (
                <span className="text-xs text-gray-400">({logs.data.data.length})</span>
              )}
            </button>
          );
        })}
      </div>

      {/* Tab content */}
      {tab === 'overview' && (
        <div className="space-y-4">
          <div className="bg-white rounded-xl shadow-sm border border-gray-200/80 p-6">
            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-4">Run Details</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-y-3 gap-x-8">
              {([
                ['Run ID', <span key="id" className="font-mono text-xs select-all">{r.run_id}</span>],
                ['Status', <StatusBadge key="st" status={r.status} />],
                ['Pipeline', r.pipeline || '—'],
                ['Workflow', r.workflow || '—'],
                ['Started', formatTimestamp(r.started_at) || '—'],
                ['Finished', formatTimestamp(r.finished_at) || '—'],
                ['Duration', formatDuration(r.duration_ms) || '—'],
              ] as [string, React.ReactNode][]).map(([label, value]) => (
                <div key={label} className="flex items-baseline gap-3 py-1.5 border-b border-gray-50">
                  <span className="text-xs font-medium text-gray-400 w-20 shrink-0">{label}</span>
                  <span className="text-sm text-gray-900">{value}</span>
                </div>
              ))}
            </div>

            {/* Inline step progress bar for workflow runs */}
            {hasWorkflow && steps.data?.data && steps.data.data.length > 0 && (
              <div className="mt-6 border-t border-gray-100 pt-4">
                <h4 className="text-xs font-medium text-gray-500 mb-2">Step Progress</h4>
                <div className="flex gap-1 rounded-lg overflow-hidden">
                  {steps.data.data.map((s) => {
                    const ss = getStatusStyle(s.status);
                    return (
                      <div
                        key={s.step_id || s.step_name}
                        className={`flex-1 h-2.5 ${ss.bg} transition-all`}
                        title={`${s.step_name}: ${s.status}${s.duration_ms ? ` (${formatDuration(s.duration_ms)})` : ''}`}
                      />
                    );
                  })}
                </div>
                <p className="text-[10px] text-gray-400 mt-1.5">
                  {steps.data.data.filter(s => s.status === 'COMPLETED').length}/{steps.data.data.length} steps completed
                </p>
              </div>
            )}
          </div>

          {/* SplitPanel: DAG (top) + Events (bottom) for workflow runs */}
          {hasWorkflow && (events.data?.data?.length ?? 0) > 0 && (
            <SplitPanel
              direction="vertical"
              defaultTopSize={55}
              minSize={25}
              className="min-h-[500px]"
              top={
                <div className="p-4">
                  <h4 className="text-xs font-medium text-gray-500 mb-2">Workflow DAG</h4>
                  <WorkflowDAG
                    steps={wSteps}
                    stepStates={stepStates}
                    height={260}
                    showMinimap={wSteps.length >= 8}
                    onStepClick={(name) => {
                      const found = wSteps.find(s => s.name === name);
                      if (found) setSelectedStep(found);
                    }}
                  />
                </div>
              }
              bottom={
                <div className="p-4">
                  <h4 className="text-xs font-medium text-gray-500 mb-2">Recent Events</h4>
                  <EventTimeline events={events.data!.data.slice(0, 20)} />
                </div>
              }
            />
          )}
        </div>
      )}

      {tab === 'graph' && hasWorkflow && (
        <div className="space-y-4">
          <div className="bg-white rounded-xl shadow-sm border border-gray-200/80 p-5">
            <WorkflowDAG
              steps={wSteps}
              stepStates={stepStates}
              height={400}
              showMinimap={wSteps.length >= 8}
              onStepClick={(name) => {
                const found = wSteps.find(s => s.name === name);
                if (found) setSelectedStep(found);
              }}
            />
            {/* Step legend */}
            <div className="flex gap-4 mt-3 text-[10px] text-gray-500">
              {['COMPLETED', 'RUNNING', 'FAILED', 'PENDING', 'SKIPPED'].map(s => {
                const ss = getStatusStyle(s);
                return (
                  <span key={s} className="flex items-center gap-1">
                    <span className={`w-2 h-2 rounded-full ${ss.dot}`} />
                    {s.charAt(0) + s.slice(1).toLowerCase()}
                  </span>
                );
              })}
            </div>
          </div>

          {/* Step timing waterfall (Gantt chart) */}
          {steps.data?.data && steps.data.data.some(s => s.duration_ms != null) && (
            <div className="bg-white rounded-xl shadow-sm border border-gray-200/80 p-5">
              <StepGanttChart
                steps={steps.data.data}
                height={Math.max(200, steps.data.data.length * 40 + 60)}
              />
            </div>
          )}
        </div>
      )}

      {tab === 'events' && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200/80 p-5">
          {events.isLoading && <Spinner />}
          {(!events.data?.data || events.data.data.length === 0) && !events.isLoading && (
            <EmptyState message="No events recorded" />
          )}
          {(events.data?.data ?? []).length > 0 && <EventTimeline events={events.data!.data} />}
        </div>
      )}

      {tab === 'logs' && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200/80 overflow-hidden">
          {logs.isLoading && <Spinner />}
          {(!logs.data?.data || logs.data.data.length === 0) && !logs.isLoading && (
            <EmptyState message="No log entries — logs are captured during execution" />
          )}
          {(logs.data?.data ?? []).length > 0 && (
            <LogViewer
              logs={logs.data!.data}
              height={500}
              follow={isActive}
              loading={logs.isLoading}
            />
          )}
        </div>
      )}

      {tab === 'params' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-white rounded-xl shadow-sm border border-gray-200/80 p-5">
            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">Parameters</h3>
            <JsonViewer data={r.params} />
          </div>
          <div className="bg-white rounded-xl shadow-sm border border-gray-200/80 p-5">
            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">Result</h3>
            <JsonViewer data={r.result} />
          </div>
        </div>
      )}

      {tab === 'errors' && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200/80 p-5">
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

      {/* Step detail drawer */}
      {selectedStep && (
        <StepDetailDrawer
          step={selectedStep}
          state={selectedStepState}
          onClose={() => setSelectedStep(null)}
        />
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
