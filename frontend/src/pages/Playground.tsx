import { useState, useCallback, useEffect, useRef } from 'react';
import { Play, Plus, Rocket, SkipForward, SkipBack, FastForward, RotateCcw, X, Code2, Sparkles } from 'lucide-react';
import CodeEditor from '../components/CodeEditor';
import PageHeader from '../components/PageHeader';
import StatusBadge from '../components/StatusBadge';
import { Button, Spinner, ErrorBox, EmptyState, Modal } from '../components/UI';
import {
  usePlaygroundWorkflows,
  usePlaygroundExamples,
  usePlaygroundContext,
  usePlaygroundHistory,
  usePlaygroundPeek,
  useCreatePlaygroundSession,
  useDeletePlaygroundSession,
  usePlaygroundStep,
  usePlaygroundStepBack,
  usePlaygroundRunAll,
  usePlaygroundReset,
  usePlaygroundSetParams,
} from '../api/hooks';
import type {
  PlaygroundExample,
  PlaygroundWorkflow,
  StepSnapshot,
} from '../types/api';

// ── Step type colors ────────────────────────────────────────────────
const STEP_TYPE_COLORS: Record<string, string> = {
  pipeline: 'bg-blue-100 text-blue-800',
  lambda: 'bg-purple-100 text-purple-800',
  wait: 'bg-yellow-100 text-yellow-800',
  choice: 'bg-orange-100 text-orange-800',
  map: 'bg-teal-100 text-teal-800',
};

function StepTypeBadge({ type }: { type: string }) {
  const cls = STEP_TYPE_COLORS[type] ?? 'bg-gray-100 text-gray-600';
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${cls}`}>
      {type}
    </span>
  );
}

// ── JSON Editor (Monaco-powered) ────────────────────────────────────
function JsonEditorPanel({
  value,
  onChange,
  label,
  readOnly = false,
  height = '120px',
}: {
  value: string;
  onChange?: (v: string) => void;
  label?: string;
  readOnly?: boolean;
  height?: string;
}) {
  const [error, setError] = useState<string | null>(null);

  const handleChange = (v: string) => {
    onChange?.(v);
    try {
      JSON.parse(v);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div>
      {label && <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">{label}</p>}
      <CodeEditor
        value={value}
        language="json"
        height={height}
        readOnly={readOnly}
        onChange={handleChange}
        minimap={false}
        showToolbar={false}
        theme="dark"
        wordWrap="on"
      />
      {error && <p className="text-xs text-red-500 mt-1">{error}</p>}
    </div>
  );
}

// ── Code Snippet viewer (Monaco-powered) ────────────────────────────
function CodeSnippet({ code, title }: { code: string; title?: string }) {
  return (
    <CodeEditor
      value={code}
      language="python"
      height="260px"
      readOnly
      fileName={title}
      showToolbar={true}
      theme="dark"
      minimap={false}
    />
  );
}

// ── Step Timeline ───────────────────────────────────────────────────
function StepTimeline({
  steps,
  history,
  currentIndex,
  onClickStep,
}: {
  steps: Array<{ name: string; type: string; pipeline: string | null; depends_on: string[] }>;
  history: StepSnapshot[];
  currentIndex: number;
  onClickStep?: (idx: number) => void;
}) {
  return (
    <div className="space-y-1">
      {steps.map((step, idx) => {
        const executed = history.find((h) => h.step_name === step.name);
        const isCurrent = idx === currentIndex;
        const isPast = idx < currentIndex;
        const isFuture = idx > currentIndex;

        let ringColor = 'border-gray-300 bg-gray-50';
        let dotColor = 'bg-gray-300';
        let textColor = 'text-gray-400';

        if (executed?.status === 'completed') {
          ringColor = 'border-green-200 bg-green-50';
          dotColor = 'bg-green-500';
          textColor = 'text-gray-900';
        } else if (executed?.status === 'failed') {
          ringColor = 'border-red-200 bg-red-50';
          dotColor = 'bg-red-500';
          textColor = 'text-gray-900';
        } else if (isCurrent) {
          ringColor = 'border-spine-300 bg-spine-50';
          dotColor = 'bg-spine-500 animate-pulse';
          textColor = 'text-gray-900';
        }

        return (
          <div
            key={step.name}
            className={`flex items-center gap-3 px-3 py-2 rounded-lg border transition-all cursor-pointer hover:shadow-sm ${ringColor}`}
            onClick={() => onClickStep?.(idx)}
          >
            {/* Step indicator dot */}
            <div className="flex flex-col items-center">
              <div className={`w-3 h-3 rounded-full ${dotColor}`} />
              {idx < steps.length - 1 && (
                <div className={`w-0.5 h-4 mt-1 ${isPast ? 'bg-green-300' : 'bg-gray-200'}`} />
              )}
            </div>

            {/* Step info */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className={`text-sm font-medium ${textColor}`}>{step.name}</span>
                <StepTypeBadge type={step.type} />
                {isCurrent && !executed && (
                  <span className="text-xs text-spine-600 font-medium">▶ next</span>
                )}
              </div>
              {step.pipeline && (
                <p className="text-xs text-gray-400 mt-0.5 truncate">{step.pipeline}</p>
              )}
              {executed && (
                <p className="text-xs text-gray-400 mt-0.5">
                  {executed.duration_ms.toFixed(1)}ms
                  {executed.error && <span className="text-red-500 ml-2">⚠ {executed.error}</span>}
                </p>
              )}
            </div>

            {/* Status icon */}
            <div className="shrink-0 text-base">
              {executed?.status === 'completed' && '✓'}
              {executed?.status === 'failed' && '✗'}
              {isCurrent && !executed && '▸'}
              {isFuture && !executed && '○'}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── Execution History Panel ─────────────────────────────────────────
function HistoryPanel({ history }: { history: StepSnapshot[] }) {
  const [expanded, setExpanded] = useState<number | null>(null);

  if (history.length === 0) {
    return <p className="text-xs text-gray-400 py-4 text-center">No steps executed yet</p>;
  }

  return (
    <div className="space-y-2">
      {history.map((snap, idx) => (
        <div key={idx} className="border border-gray-200 rounded-lg overflow-hidden">
          <button
            className="w-full flex items-center justify-between px-3 py-2 bg-gray-50 hover:bg-gray-100 transition-colors text-left"
            onClick={() => setExpanded(expanded === idx ? null : idx)}
          >
            <div className="flex items-center gap-2">
              <StatusBadge status={snap.status} />
              <span className="text-sm font-medium text-gray-800">{snap.step_name}</span>
              <StepTypeBadge type={snap.step_type} />
            </div>
            <span className="text-xs text-gray-400">{snap.duration_ms.toFixed(1)}ms</span>
          </button>

          {expanded === idx && (
            <div className="px-3 py-3 border-t border-gray-100 space-y-3">
              {snap.error && (
                <div className="bg-red-50 border border-red-200 rounded p-2 text-xs text-red-700">
                  {snap.error}
                </div>
              )}
              {snap.result && (
                <div>
                  <p className="text-xs font-medium text-gray-500 mb-1">Output</p>
                  <CodeEditor
                    value={JSON.stringify(snap.result.output, null, 2)}
                    language="json"
                    height="100px"
                    readOnly
                    showToolbar={false}
                    minimap={false}
                    theme="light"
                    lineNumbers={false}
                  />
                </div>
              )}
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <p className="text-xs font-medium text-gray-500 mb-1">Context Before</p>
                  <CodeEditor
                    value={JSON.stringify(snap.context_before, null, 2)}
                    language="json"
                    height="90px"
                    readOnly
                    showToolbar={false}
                    minimap={false}
                    theme="light"
                    lineNumbers={false}
                  />
                </div>
                <div>
                  <p className="text-xs font-medium text-gray-500 mb-1">Context After</p>
                  <CodeEditor
                    value={JSON.stringify(snap.context_after, null, 2)}
                    language="json"
                    height="90px"
                    readOnly
                    showToolbar={false}
                    minimap={false}
                    theme="light"
                    lineNumbers={false}
                  />
                </div>
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ── Example Card ────────────────────────────────────────────────────
function ExampleCard({
  example,
  onLoad,
}: {
  example: PlaygroundExample;
  onLoad: (ex: PlaygroundExample) => void;
}) {
  const [showCode, setShowCode] = useState(false);

  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-sm hover:shadow transition-shadow">
      <div className="p-4">
        <div className="flex items-start justify-between">
          <div>
            <h3 className="text-sm font-bold text-gray-900">{example.title}</h3>
            <p className="text-xs text-gray-500 mt-1">{example.description}</p>
          </div>
          <span className="text-xs bg-gray-100 text-gray-600 rounded px-2 py-0.5">{example.category}</span>
        </div>

        <div className="flex items-center gap-2 mt-3">
          <Button variant="primary" size="xs" onClick={() => onLoad(example)}>
            <Play className="w-3 h-3 mr-1" />Load in Playground
          </Button>
          {example.code_snippet && (
            <Button variant="secondary" size="xs" onClick={() => setShowCode(!showCode)}>
              <Code2 className="w-3 h-3 mr-1" />{showCode ? 'Hide Code' : 'View Code'}
            </Button>
          )}
        </div>
      </div>

      {showCode && example.code_snippet && (
        <div className="border-t border-gray-100 p-3">
          <CodeSnippet code={example.code_snippet} title={`${example.workflow_name}.py`} />
        </div>
      )}
    </div>
  );
}

// ── Workflow Picker Modal ───────────────────────────────────────────
function WorkflowPickerModal({
  workflows,
  onSelect,
  onClose,
}: {
  workflows: PlaygroundWorkflow[];
  onSelect: (wf: PlaygroundWorkflow) => void;
  onClose: () => void;
}) {
  return (
    <Modal title="Choose a Workflow" onClose={onClose} maxWidth="max-w-2xl">
      <div className="space-y-2 max-h-96 overflow-y-auto">
        {workflows.map((wf) => (
          <button
            key={wf.name}
            className="w-full text-left p-3 rounded-xl border border-gray-200 hover:border-spine-300 hover:bg-spine-50 transition-all"
            onClick={() => onSelect(wf)}
          >
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-gray-900">{wf.name}</span>
              <span className="text-xs text-gray-400">{wf.step_count} steps</span>
            </div>
            {wf.description && (
              <p className="text-xs text-gray-500 mt-1">{wf.description}</p>
            )}
            <div className="flex gap-1 mt-2">
              {wf.tags.map((t) => (
                <span key={t} className="text-xs bg-gray-100 text-gray-600 rounded px-1.5 py-0.5">
                  {t}
                </span>
              ))}
            </div>
          </button>
        ))}
        {workflows.length === 0 && (
          <EmptyState message="No workflows registered. Register workflows in the API first." />
        )}
      </div>
    </Modal>
  );
}

// ═══════════════════════════════════════════════════════════════════
// MAIN PLAYGROUND PAGE
// ═══════════════════════════════════════════════════════════════════

type PlaygroundView = 'launcher' | 'active';

export default function Playground() {
  // ── State ───────────────────────────────────────────────────────
  const [view, setView] = useState<PlaygroundView>('launcher');
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [activeWorkflow, setActiveWorkflow] = useState<PlaygroundWorkflow | null>(null);
  const [showWorkflowPicker, setShowWorkflowPicker] = useState(false);
  const [paramsJson, setParamsJson] = useState('{}');
  const [outputLog, setOutputLog] = useState<string[]>([]);
  const logRef = useRef<HTMLDivElement>(null);

  // ── Queries ─────────────────────────────────────────────────────
  const workflowsQ = usePlaygroundWorkflows();
  const examplesQ = usePlaygroundExamples();
  const contextQ = usePlaygroundContext(activeSessionId ?? '');
  const historyQ = usePlaygroundHistory(activeSessionId ?? '');
  const peekQ = usePlaygroundPeek(activeSessionId ?? '');

  // ── Mutations ───────────────────────────────────────────────────
  const createSession = useCreatePlaygroundSession();
  const deleteSession = useDeletePlaygroundSession();
  const stepMut = usePlaygroundStep();
  const stepBackMut = usePlaygroundStepBack();
  const runAllMut = usePlaygroundRunAll();
  const resetMut = usePlaygroundReset();
  const setParamsMut = usePlaygroundSetParams();

  const workflows = workflowsQ.data?.data ?? [];
  const examples = examplesQ.data?.data ?? [];
  const context = contextQ.data?.data ?? null;
  const history = historyQ.data?.data ?? [];
  const nextStep = peekQ.data?.data ?? null;

  // ── Auto-scroll output log ────────────────────────────────────
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [outputLog]);

  // ── Helpers ───────────────────────────────────────────────────
  const log = useCallback((msg: string) => {
    const ts = new Date().toLocaleTimeString();
    setOutputLog((prev) => [...prev, `[${ts}] ${msg}`]);
  }, []);

  const refetchSessionData = useCallback(() => {
    contextQ.refetch();
    historyQ.refetch();
    peekQ.refetch();
  }, [contextQ, historyQ, peekQ]);

  // ── Session lifecycle ─────────────────────────────────────────
  const handleStartSession = async (workflowName: string, params: Record<string, unknown>) => {
    try {
      const result = await createSession.mutateAsync({
        workflow_name: workflowName,
        params,
      });
      const session = result.data;
      setActiveSessionId(session.session_id);
      setView('active');
      setOutputLog([]);
      log(`Session ${session.session_id} created — ${session.total_steps} steps loaded`);
      log(`Workflow: ${session.workflow_name}`);
      log(`Mode: dry-run (pipeline steps return stubs)`);
      log('─────────────────────────────────');
      log('Press ▶ Step to execute the next step');
    } catch (err) {
      log(`Error: ${err instanceof Error ? err.message : String(err)}`);
    }
  };

  const handleLoadExample = (example: PlaygroundExample) => {
    setParamsJson(JSON.stringify(example.params, null, 2));
    handleStartSession(example.workflow_name, example.params);
  };

  const handleLoadWorkflow = (wf: PlaygroundWorkflow) => {
    setShowWorkflowPicker(false);
    const params = JSON.parse(paramsJson || '{}');
    setActiveWorkflow(wf);
    handleStartSession(wf.name, params);
  };

  const handleEndSession = async () => {
    if (activeSessionId) {
      await deleteSession.mutateAsync(activeSessionId);
      log(`Session ${activeSessionId} destroyed`);
    }
    setActiveSessionId(null);
    setActiveWorkflow(null);
    setView('launcher');
  };

  // ── Step controls ─────────────────────────────────────────────
  const handleStep = async () => {
    if (!activeSessionId) return;
    try {
      const result = await stepMut.mutateAsync(activeSessionId);
      const snap = result.data;
      const statusIcon = snap.status === 'completed' ? '✓' : '✗';
      log(`${statusIcon} Step "${snap.step_name}" (${snap.step_type}) → ${snap.status} [${snap.duration_ms.toFixed(1)}ms]`);
      if (snap.error) log(`  Error: ${snap.error}`);
      if (snap.result?.output) log(`  Output: ${JSON.stringify(snap.result.output)}`);
      refetchSessionData();
    } catch (err) {
      log(`Error: ${err instanceof Error ? err.message : String(err)}`);
    }
  };

  const handleStepBack = async () => {
    if (!activeSessionId) return;
    try {
      const result = await stepBackMut.mutateAsync(activeSessionId);
      const snap = result.data;
      if (snap) {
        log(`◀ Rewound step "${snap.step_name}" — context restored`);
      } else {
        log('Nothing to undo');
      }
      refetchSessionData();
    } catch (err) {
      log(`Error: ${err instanceof Error ? err.message : String(err)}`);
    }
  };

  const handleRunAll = async () => {
    if (!activeSessionId) return;
    try {
      log('▶▶ Running all remaining steps...');
      const result = await runAllMut.mutateAsync(activeSessionId);
      const snaps = result.data;
      for (const snap of snaps) {
        const icon = snap.status === 'completed' ? '✓' : '✗';
        log(`  ${icon} "${snap.step_name}" → ${snap.status} [${snap.duration_ms.toFixed(1)}ms]`);
      }
      log(`Done — ${snaps.length} steps executed`);
      refetchSessionData();
    } catch (err) {
      log(`Error: ${err instanceof Error ? err.message : String(err)}`);
    }
  };

  const handleReset = async () => {
    if (!activeSessionId) return;
    try {
      await resetMut.mutateAsync(activeSessionId);
      setOutputLog([]);
      log('↺ Session reset — workflow reloaded from initial state');
      log('─────────────────────────────────');
      refetchSessionData();
    } catch (err) {
      log(`Error: ${err instanceof Error ? err.message : String(err)}`);
    }
  };

  const handleApplyParams = async () => {
    if (!activeSessionId) return;
    try {
      const params = JSON.parse(paramsJson);
      await setParamsMut.mutateAsync({ sid: activeSessionId, params });
      log(`✎ Params updated: ${Object.keys(params).join(', ')}`);
      refetchSessionData();
    } catch (err) {
      log(`Error: ${err instanceof Error ? err.message : String(err)}`);
    }
  };

  // ── Loading state ─────────────────────────────────────────────
  if (workflowsQ.isLoading) return <Spinner />;
  if (workflowsQ.isError) {
    return <ErrorBox message="Failed to load playground" detail={String(workflowsQ.error)} />;
  }

  // ═══════════════════════════════════════════════════════════════
  // LAUNCHER VIEW — pick a workflow or example
  // ═══════════════════════════════════════════════════════════════
  if (view === 'launcher') {
    return (
      <div>
        <PageHeader
          title="Workflow Playground"
          description="Interactive REPL — step through workflows, inspect context, modify params, and replay steps. No setup required."
        />

        {/* Quick-start bar */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200/80 p-5 mb-6">
          <div className="flex items-center gap-4">
            <div className="flex-1">
              <h3 className="text-sm font-bold text-gray-800 mb-1 flex items-center gap-1.5"><Rocket className="w-4 h-4 text-spine-500" />Quick Start</h3>
              <p className="text-xs text-gray-500">
                Choose a registered workflow or load a pre-built example to experiment with.
              </p>
            </div>
            <Button onClick={() => setShowWorkflowPicker(true)}>
              <Plus className="w-3.5 h-3.5 mr-1" />New Session
            </Button>
          </div>
        </div>

        {/* Examples grid */}
        <div className="mb-6">
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3 flex items-center gap-1.5">
            <Sparkles className="w-3.5 h-3.5" />Examples
          </h3>
          <p className="text-sm text-gray-500 mb-4">
            Click "Load in Playground" to start an interactive session with pre-configured params.
            View the Python code to see how each workflow is defined.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {examples.map((ex) => (
              <ExampleCard key={ex.id} example={ex} onLoad={handleLoadExample} />
            ))}
          </div>
          {examples.length === 0 && (
            <EmptyState message="No playground examples available" />
          )}
        </div>

        {/* Registered workflows */}
        <div>
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">Registered Workflows</h3>
          <div className="bg-white rounded-xl shadow-sm border border-gray-200/80 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50/80 border-b border-gray-200">
                  <th className="text-left px-5 py-2.5 text-xs font-medium text-gray-500 uppercase tracking-wider">Workflow</th>
                  <th className="text-left px-5 py-2.5 text-xs font-medium text-gray-500 uppercase tracking-wider">Domain</th>
                  <th className="text-left px-5 py-2.5 text-xs font-medium text-gray-500 uppercase tracking-wider">Steps</th>
                  <th className="text-left px-5 py-2.5 text-xs font-medium text-gray-500 uppercase tracking-wider">Tags</th>
                  <th className="text-right px-5 py-2.5 text-xs font-medium text-gray-500 uppercase tracking-wider">Action</th>
                </tr>
              </thead>
              <tbody>
                {workflows.map((wf) => (
                  <tr key={wf.name} className="border-b border-gray-100 hover:bg-gray-50/50 transition-colors">
                    <td className="px-5 py-3">
                      <span className="font-medium text-gray-900">{wf.name}</span>
                      {wf.description && <p className="text-xs text-gray-400 mt-0.5">{wf.description}</p>}
                    </td>
                    <td className="px-5 py-3 text-xs text-gray-500">{wf.domain || '—'}</td>
                    <td className="px-5 py-3 text-xs text-gray-500">{wf.step_count}</td>
                    <td className="px-5 py-3">
                      <div className="flex gap-1 flex-wrap">
                        {wf.tags.map((t) => (
                          <span key={t} className="text-xs bg-gray-100 text-gray-600 rounded px-1.5 py-0.5">{t}</span>
                        ))}
                      </div>
                    </td>
                    <td className="px-5 py-3 text-right">
                      <Button
                        variant="primary"
                        size="xs"
                        onClick={() => {
                          setActiveWorkflow(wf);
                          handleStartSession(wf.name, {});
                        }}
                      >
                        <Play className="w-3 h-3 mr-1" />Launch
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {workflows.length === 0 && (
              <EmptyState message="No workflows registered" />
            )}
          </div>
        </div>

        {/* Workflow picker modal */}
        {showWorkflowPicker && (
          <WorkflowPickerModal
            workflows={workflows}
            onSelect={handleLoadWorkflow}
            onClose={() => setShowWorkflowPicker(false)}
          />
        )}
      </div>
    );
  }

  // ═══════════════════════════════════════════════════════════════
  // ACTIVE SESSION VIEW — the interactive playground
  // ═══════════════════════════════════════════════════════════════
  const sessionComplete = (historyQ.data?.data?.length ?? 0) >= (activeWorkflow?.step_count ?? 999);
  const isBusy = stepMut.isPending || stepBackMut.isPending || runAllMut.isPending || resetMut.isPending;

  return (
    <div className="h-full flex flex-col">
      {/* Header with session controls */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-xl font-bold text-gray-900 flex items-center gap-2">
            <Play className="w-5 h-5 text-spine-600" />
            Playground
            {activeWorkflow && (
              <span className="text-base font-normal text-gray-500">
                — {activeWorkflow.name}
              </span>
            )}
          </h2>
          {activeSessionId && (
            <p className="text-xs text-gray-400 mt-0.5">
              Session: {activeSessionId} · Dry-run mode
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" size="xs" onClick={handleReset} disabled={isBusy}>
            <RotateCcw className="w-3 h-3 mr-1" />Reset
          </Button>
          <Button variant="danger" size="xs" onClick={handleEndSession}>
            <X className="w-3 h-3 mr-1" />End Session
          </Button>
        </div>
      </div>

      {/* Main 3-column layout */}
      <div className="flex-1 grid grid-cols-12 gap-4 min-h-0">
        {/* ── LEFT: Step Timeline ─────────────────────────────── */}
        <div className="col-span-3 flex flex-col min-h-0">
          <div className="bg-white rounded-xl shadow-sm border border-gray-200/80 flex-1 flex flex-col min-h-0">
            <div className="px-4 py-3 border-b border-gray-100">
              <h3 className="text-sm font-bold text-gray-800">Steps</h3>
              <p className="text-xs text-gray-400 mt-0.5">
                {history.length} / {activeWorkflow?.step_count ?? 0} executed
              </p>
            </div>
            <div className="flex-1 overflow-y-auto p-3">
              {activeWorkflow && (
                <StepTimeline
                  steps={activeWorkflow.steps}
                  history={history}
                  currentIndex={history.length}
                />
              )}
            </div>

            {/* Step control buttons */}
            <div className="border-t border-gray-100 p-3 space-y-2">
              <div className="grid grid-cols-3 gap-2">
                <Button
                  variant="secondary"
                  size="xs"
                  onClick={handleStepBack}
                  disabled={isBusy || history.length === 0}
                >
                  <SkipBack className="w-3 h-3 mr-1" />Back
                </Button>
                <Button
                  variant="primary"
                  size="xs"
                  onClick={handleStep}
                  disabled={isBusy || sessionComplete}
                >
                  <SkipForward className="w-3 h-3 mr-1" />Step
                </Button>
                <Button
                  variant="secondary"
                  size="xs"
                  onClick={handleRunAll}
                  disabled={isBusy || sessionComplete}
                >
                  <FastForward className="w-3 h-3 mr-1" />All
                </Button>
              </div>
              {sessionComplete && (
                <p className="text-xs text-green-600 text-center font-medium">✓ All steps complete</p>
              )}
            </div>
          </div>
        </div>

        {/* ── CENTER: Output / REPL ───────────────────────────── */}
        <div className="col-span-5 flex flex-col min-h-0 gap-4">
          {/* Output console */}
          <div className="bg-gray-900 rounded-xl shadow-sm flex-1 flex flex-col min-h-0">
            <div className="flex items-center justify-between px-4 py-2 bg-gray-800 rounded-t-xl">
              <span className="text-xs text-gray-400 font-medium">Output Console</span>
              <button
                onClick={() => setOutputLog([])}
                className="text-xs text-gray-500 hover:text-gray-300 transition-colors"
              >
                Clear
              </button>
            </div>
            <div ref={logRef} className="flex-1 overflow-y-auto p-4 min-h-0">
              {outputLog.length === 0 ? (
                <p className="text-gray-600 text-xs">
                  Waiting for actions... Press ▶ Step to begin.
                </p>
              ) : (
                outputLog.map((line, i) => (
                  <pre
                    key={i}
                    className={`text-xs font-mono leading-relaxed whitespace-pre-wrap ${
                      line.includes('✓') ? 'text-green-400'
                        : line.includes('✗') || line.includes('Error') ? 'text-red-400'
                        : line.includes('◀') || line.includes('↺') ? 'text-yellow-400'
                        : line.includes('✎') ? 'text-blue-400'
                        : line.includes('▶') ? 'text-cyan-400'
                        : 'text-gray-300'
                    }`}
                  >
                    {line}
                  </pre>
                ))
              )}
            </div>
          </div>

          {/* Execution history */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-200/80 max-h-64 overflow-hidden flex flex-col">
            <div className="px-4 py-2 border-b border-gray-100 shrink-0">
              <h3 className="text-sm font-bold text-gray-800">Execution History</h3>
            </div>
            <div className="flex-1 overflow-y-auto p-3">
              <HistoryPanel history={history} />
            </div>
          </div>
        </div>

        {/* ── RIGHT: Context / Params ─────────────────────────── */}
        <div className="col-span-4 flex flex-col min-h-0 gap-4">
          {/* Params editor */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-200/80">
            <div className="px-4 py-2 border-b border-gray-100 flex items-center justify-between">
              <h3 className="text-sm font-bold text-gray-800">Parameters</h3>
              <Button variant="primary" size="xs" onClick={handleApplyParams} disabled={isBusy}>
                Apply
              </Button>
            </div>
            <div className="p-3">
              <JsonEditorPanel
                value={paramsJson}
                onChange={setParamsJson}
                height="120px"
              />
              <p className="text-xs text-gray-400 mt-2">
                Edit JSON above and click Apply to update params before the next step.
              </p>
            </div>
          </div>

          {/* Current context */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-200/80 flex-1 flex flex-col min-h-0">
            <div className="px-4 py-2 border-b border-gray-100">
              <h3 className="text-sm font-bold text-gray-800">Context</h3>
            </div>
            <div className="flex-1 overflow-y-auto p-3 space-y-3">
              {context ? (
                <>
                  <div>
                    <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Run ID</p>
                    <p className="text-xs font-mono text-gray-700">{context.run_id}</p>
                  </div>
                  <div>
                    <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Params</p>
                    <CodeEditor
                      value={JSON.stringify(context.params, null, 2)}
                      language="json"
                      height="90px"
                      readOnly
                      showToolbar={false}
                      minimap={false}
                      theme="dark"
                      lineNumbers={false}
                    />
                  </div>
                  <div>
                    <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">
                      Outputs ({Object.keys(context.outputs).length} steps)
                    </p>
                    <CodeEditor
                      value={JSON.stringify(context.outputs, null, 2)}
                      language="json"
                      height="140px"
                      readOnly
                      showToolbar={false}
                      minimap={false}
                      theme="dark"
                      lineNumbers={false}
                    />
                  </div>
                </>
              ) : (
                <p className="text-xs text-gray-400 text-center py-4">
                  Context will appear after the first step
                </p>
              )}
            </div>
          </div>

          {/* Next step preview */}
          {nextStep && (
            <div className="bg-spine-50 rounded-xl border border-spine-200 p-3">
              <p className="text-xs font-medium text-spine-700 uppercase tracking-wide mb-1">Next Step</p>
              <div className="flex items-center gap-2">
                <span className="text-sm font-bold text-spine-900">{nextStep.name}</span>
                <StepTypeBadge type={nextStep.step_type} />
              </div>
              {nextStep.pipeline_name && (
                <p className="text-xs text-spine-600 mt-1">Pipeline: {nextStep.pipeline_name}</p>
              )}
              {nextStep.depends_on.length > 0 && (
                <p className="text-xs text-spine-500 mt-0.5">
                  Depends on: {nextStep.depends_on.join(', ')}
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
