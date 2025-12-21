/**
 * Functions Console — AWS Lambda-inspired function management and execution.
 *
 * Features:
 * - Function list with search/filter/tags
 * - Monaco code editor for source editing
 * - Event JSON editor for invocation payloads
 * - Real-time execution with Lambda-style logs
 * - Template gallery for quick-start
 * - Configuration panel (timeout, memory, runtime, env vars)
 * - Invocation history with duration/status
 */

import { useState, useCallback, useEffect } from 'react';
import {
  Zap,
  Plus,
  Play,
  Save,
  Trash2,
  Settings2,
  Clock,
  Tag,
  Search,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  RotateCw,
  FileCode2,
  Terminal,
  Copy,
  Check,
  Layers,
  Activity,
  Timer,
  Cpu,
  Variable,
  type LucideIcon,
} from 'lucide-react';
import PageHeader from '../components/PageHeader';
import { Button, Spinner, ErrorBox, EmptyState, Modal } from '../components/UI';
import CodeEditor from '../components/CodeEditor';
import {
  useFunctions,
  useFunction,
  useCreateFunction,
  useUpdateFunction,
  useDeleteFunction,
  useInvokeFunction,
  useFunctionLogs,
  useFunctionTemplates,
} from '../api/hooks';
import type {
  FunctionSummary,
  FunctionDetail,
  FunctionTemplate,
  InvokeResult,
  InvocationLog,
} from '../types/api';

// ── Status indicator ───────────────────────────────────────────────

function FnStatusBadge({ status }: { status: string }) {
  const config: Record<string, { bg: string; text: string; dot: string; animate?: boolean }> = {
    idle:    { bg: 'bg-gray-50',    text: 'text-gray-600',    dot: 'bg-gray-400' },
    running: { bg: 'bg-blue-50',    text: 'text-blue-700',    dot: 'bg-blue-500', animate: true },
    error:   { bg: 'bg-red-50',     text: 'text-red-700',     dot: 'bg-red-500' },
    success: { bg: 'bg-emerald-50', text: 'text-emerald-700', dot: 'bg-emerald-500' },
  };
  const c = config[status] || config.idle;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium ${c.bg} ${c.text}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${c.dot} ${c.animate ? 'animate-pulse' : ''}`} />
      {status}
    </span>
  );
}

// ── Tag pill ───────────────────────────────────────────────────────

function TagPill({ tag, onClick }: { tag: string; onClick?: () => void }) {
  return (
    <button
      onClick={onClick}
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-medium bg-spine-50 text-spine-700 border border-spine-200 hover:bg-spine-100 transition-colors"
    >
      <Tag className="w-2.5 h-2.5" />
      {tag}
    </button>
  );
}

// ── Function list item ─────────────────────────────────────────────

function FunctionListItem({
  fn,
  isSelected,
  onSelect,
}: {
  fn: FunctionSummary;
  isSelected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      onClick={onSelect}
      className={`w-full text-left px-4 py-3 border-b border-gray-100 transition-all duration-150 group ${
        isSelected
          ? 'bg-spine-50 border-l-2 border-l-spine-500'
          : 'hover:bg-gray-50 border-l-2 border-l-transparent'
      }`}
    >
      <div className="flex items-center justify-between mb-1">
        <span className={`text-sm font-medium ${isSelected ? 'text-spine-700' : 'text-gray-900'}`}>
          {fn.name}
        </span>
        <FnStatusBadge status={fn.status} />
      </div>
      <p className="text-xs text-gray-500 line-clamp-1 mb-1.5">{fn.description || 'No description'}</p>
      <div className="flex items-center gap-3 text-[10px] text-gray-400">
        <span className="flex items-center gap-1">
          <FileCode2 className="w-3 h-3" />
          {fn.source_lines} lines
        </span>
        <span className="flex items-center gap-1">
          <Activity className="w-3 h-3" />
          {fn.invoke_count} invocations
        </span>
        <span className="flex items-center gap-1">
          <Clock className="w-3 h-3" />
          {fn.timeout}s
        </span>
      </div>
    </button>
  );
}

// ── Config panel ───────────────────────────────────────────────────

function ConfigPanel({
  config,
  onChange,
  readOnly = false,
}: {
  config: { timeout: number; memory_mb: number; runtime: string; handler: string; env_vars: Record<string, string> };
  onChange: (key: string, value: unknown) => void;
  readOnly?: boolean;
}) {
  const [newKey, setNewKey] = useState('');
  const [newVal, setNewVal] = useState('');

  const addEnvVar = () => {
    if (!newKey.trim()) return;
    onChange('env_vars', { ...config.env_vars, [newKey.trim()]: newVal });
    setNewKey('');
    setNewVal('');
  };

  const removeEnvVar = (key: string) => {
    const { [key]: _, ...rest } = config.env_vars;
    onChange('env_vars', rest);
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-[11px] font-medium text-gray-500 uppercase tracking-wider mb-1">
            <Timer className="w-3 h-3 inline mr-1" />Timeout (seconds)
          </label>
          <input
            type="number"
            min={1}
            max={300}
            value={config.timeout}
            onChange={(e) => onChange('timeout', Number(e.target.value))}
            disabled={readOnly}
            className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:ring-2 focus:ring-spine-500 focus:border-spine-500 disabled:bg-gray-50"
          />
        </div>
        <div>
          <label className="block text-[11px] font-medium text-gray-500 uppercase tracking-wider mb-1">
            <Cpu className="w-3 h-3 inline mr-1" />Memory (MB)
          </label>
          <select
            value={config.memory_mb}
            onChange={(e) => onChange('memory_mb', Number(e.target.value))}
            disabled={readOnly}
            className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:ring-2 focus:ring-spine-500 focus:border-spine-500 disabled:bg-gray-50"
          >
            {[64, 128, 256, 512, 1024].map((m) => (
              <option key={m} value={m}>{m} MB</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-[11px] font-medium text-gray-500 uppercase tracking-wider mb-1">
            Runtime
          </label>
          <input
            type="text"
            value={config.runtime}
            onChange={(e) => onChange('runtime', e.target.value)}
            disabled={readOnly}
            className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:ring-2 focus:ring-spine-500 focus:border-spine-500 disabled:bg-gray-50"
          />
        </div>
        <div>
          <label className="block text-[11px] font-medium text-gray-500 uppercase tracking-wider mb-1">
            Handler
          </label>
          <input
            type="text"
            value={config.handler}
            onChange={(e) => onChange('handler', e.target.value)}
            disabled={readOnly}
            className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:ring-2 focus:ring-spine-500 focus:border-spine-500 disabled:bg-gray-50"
          />
        </div>
      </div>

      {/* Environment Variables */}
      <div>
        <label className="block text-[11px] font-medium text-gray-500 uppercase tracking-wider mb-2">
          <Variable className="w-3 h-3 inline mr-1" />Environment Variables
        </label>
        {Object.entries(config.env_vars).map(([k, v]) => (
          <div key={k} className="flex items-center gap-2 mb-1.5">
            <span className="text-xs font-mono bg-gray-50 px-2 py-1 rounded border border-gray-200 min-w-[120px]">{k}</span>
            <span className="text-xs text-gray-400">=</span>
            <span className="text-xs font-mono bg-gray-50 px-2 py-1 rounded border border-gray-200 flex-1 truncate">{v}</span>
            {!readOnly && (
              <button onClick={() => removeEnvVar(k)} className="text-gray-400 hover:text-red-500 transition-colors">
                <Trash2 className="w-3 h-3" />
              </button>
            )}
          </div>
        ))}
        {!readOnly && (
          <div className="flex items-center gap-2 mt-2">
            <input
              placeholder="KEY"
              value={newKey}
              onChange={(e) => setNewKey(e.target.value)}
              className="w-28 px-2 py-1 text-xs font-mono border border-gray-200 rounded focus:ring-1 focus:ring-spine-500"
            />
            <span className="text-xs text-gray-400">=</span>
            <input
              placeholder="value"
              value={newVal}
              onChange={(e) => setNewVal(e.target.value)}
              className="flex-1 px-2 py-1 text-xs font-mono border border-gray-200 rounded focus:ring-1 focus:ring-spine-500"
              onKeyDown={(e) => e.key === 'Enter' && addEnvVar()}
            />
            <Button size="xs" variant="ghost" onClick={addEnvVar}>
              <Plus className="w-3 h-3" />
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Log viewer ─────────────────────────────────────────────────────

function LogViewer({ logs, isLoading }: { logs: string; isLoading?: boolean }) {
  const [copied, setCopied] = useState(false);

  const copyLogs = () => {
    navigator.clipboard.writeText(logs);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="bg-[#0D1117] rounded-lg overflow-hidden border border-gray-800">
      <div className="flex items-center justify-between px-4 py-2 bg-[#161B22] border-b border-gray-800">
        <div className="flex items-center gap-2 text-xs text-gray-400">
          <Terminal className="w-3.5 h-3.5" />
          Execution Output
          {isLoading && <RotateCw className="w-3 h-3 animate-spin text-blue-400" />}
        </div>
        <button
          onClick={copyLogs}
          className="text-gray-500 hover:text-gray-300 transition-colors"
          title="Copy logs"
        >
          {copied ? <Check className="w-3.5 h-3.5 text-green-400" /> : <Copy className="w-3.5 h-3.5" />}
        </button>
      </div>
      <pre className="p-4 text-xs font-mono text-gray-300 overflow-x-auto max-h-[400px] overflow-y-auto whitespace-pre-wrap leading-relaxed">
        {logs || <span className="text-gray-600 italic">No output yet. Click Test to execute.</span>}
      </pre>
    </div>
  );
}

// ── Invocation history table ───────────────────────────────────────

function InvocationHistory({ functionId }: { functionId: string }) {
  const { data, isLoading } = useFunctionLogs(functionId, 20);
  const logs: InvocationLog[] = data?.data ?? [];

  if (isLoading) return <Spinner />;
  if (logs.length === 0) return <EmptyState message="No invocation history yet" />;

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-gray-200">
            <th className="text-left py-2 px-3 font-medium text-gray-500 uppercase tracking-wider">Request ID</th>
            <th className="text-left py-2 px-3 font-medium text-gray-500 uppercase tracking-wider">Status</th>
            <th className="text-left py-2 px-3 font-medium text-gray-500 uppercase tracking-wider">Duration</th>
            <th className="text-left py-2 px-3 font-medium text-gray-500 uppercase tracking-wider">Event</th>
            <th className="text-left py-2 px-3 font-medium text-gray-500 uppercase tracking-wider">Time</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {logs.map((log) => (
            <tr key={log.request_id} className="hover:bg-gray-50 transition-colors">
              <td className="py-2 px-3 font-mono text-gray-600">{log.request_id}</td>
              <td className="py-2 px-3">
                <FnStatusBadge status={log.status} />
              </td>
              <td className="py-2 px-3 text-gray-700">{log.duration_ms.toFixed(1)} ms</td>
              <td className="py-2 px-3 text-gray-500 truncate max-w-[200px]">{log.event_summary}</td>
              <td className="py-2 px-3 text-gray-500">
                {new Date(log.timestamp).toLocaleString()}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Template gallery ───────────────────────────────────────────────

function TemplateGallery({
  onSelect,
  onClose,
}: {
  onSelect: (template: FunctionTemplate) => void;
  onClose: () => void;
}) {
  const { data, isLoading } = useFunctionTemplates();
  const templates: FunctionTemplate[] = data?.data ?? [];

  return (
    <Modal title="Function Templates" onClose={onClose} maxWidth="max-w-2xl">
      {isLoading ? (
        <Spinner />
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {templates.map((t) => (
            <button
              key={t.id}
              onClick={() => { onSelect(t); onClose(); }}
              className="text-left p-4 rounded-xl border border-gray-200 hover:border-spine-300 hover:bg-spine-50/50 transition-all group"
            >
              <div className="flex items-center gap-2 mb-1">
                <Layers className="w-4 h-4 text-spine-500" />
                <span className="text-sm font-medium text-gray-900 group-hover:text-spine-700">{t.name}</span>
              </div>
              <p className="text-xs text-gray-500 line-clamp-2 mb-2">{t.description}</p>
              <div className="flex items-center gap-2">
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-600">{t.category}</span>
                {t.tags.slice(0, 2).map((tag) => (
                  <span key={tag} className="text-[10px] px-1.5 py-0.5 rounded bg-spine-50 text-spine-600">{tag}</span>
                ))}
              </div>
            </button>
          ))}
        </div>
      )}
    </Modal>
  );
}

// ── Create function modal ──────────────────────────────────────────

function CreateFunctionModal({
  onClose,
  onCreate,
  template,
}: {
  onClose: () => void;
  onCreate: (name: string, description: string, source: string, tags: string[]) => void;
  template?: FunctionTemplate | null;
}) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState(template?.description ?? '');
  const [tags, setTags] = useState(template?.tags.join(', ') ?? '');

  return (
    <Modal title="Create Function" onClose={onClose}>
      <div className="space-y-4">
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Function Name</label>
          <input
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="my_function"
            className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:ring-2 focus:ring-spine-500 focus:border-spine-500"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Description</label>
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What does this function do?"
            className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:ring-2 focus:ring-spine-500 focus:border-spine-500"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Tags (comma-separated)</label>
          <input
            value={tags}
            onChange={(e) => setTags(e.target.value)}
            placeholder="etl, data, example"
            className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:ring-2 focus:ring-spine-500 focus:border-spine-500"
          />
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button
            onClick={() => onCreate(
              name,
              description,
              template?.source ?? `"""${name}"""\n\ndef handler(event, context):\n    return {"statusCode": 200, "body": "Hello!"}\n`,
              tags.split(',').map((t) => t.trim()).filter(Boolean),
            )}
            disabled={!name.trim()}
          >
            <Plus className="w-4 h-4 mr-1" />
            Create
          </Button>
        </div>
      </div>
    </Modal>
  );
}

// ── Main Functions Page ────────────────────────────────────────────

type DetailTab = 'code' | 'test' | 'config' | 'history';

export default function Functions() {
  // List state
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<DetailTab>('code');

  // Editor state
  const [editedSource, setEditedSource] = useState<string | null>(null);
  const [isDirty, setIsDirty] = useState(false);

  // Test state
  const [eventJson, setEventJson] = useState('{\n  "name": "World"\n}');
  const [lastResult, setLastResult] = useState<InvokeResult | null>(null);

  // Modal state
  const [showCreate, setShowCreate] = useState(false);
  const [showTemplates, setShowTemplates] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState<FunctionTemplate | null>(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  // Queries
  const { data: listData, isLoading: listLoading, error: listError } = useFunctions({ search: searchQuery || undefined });
  const { data: detailData, isLoading: detailLoading } = useFunction(selectedId ?? '');
  const createFn = useCreateFunction();
  const updateFn = useUpdateFunction();
  const deleteFn = useDeleteFunction();
  const invokeFn = useInvokeFunction();

  const functions: FunctionSummary[] = listData?.data ?? [];
  const detail: FunctionDetail | null = detailData?.data ?? null;

  // Sync editor source when function detail loads
  useEffect(() => {
    if (detail && !isDirty) {
      setEditedSource(detail.source);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detail?.id, detail?.source]);

  // Auto-select first function
  useEffect(() => {
    if (!selectedId && functions.length > 0) {
      setSelectedId(functions[0].id);
    }
  }, [functions, selectedId]);

  const handleSave = useCallback(async () => {
    if (!selectedId || !editedSource) return;
    await updateFn.mutateAsync({ id: selectedId, body: { source: editedSource } });
    setIsDirty(false);
  }, [selectedId, editedSource, updateFn]);

  const handleInvoke = useCallback(async () => {
    if (!selectedId) return;
    let event: Record<string, unknown> = {};
    try {
      event = JSON.parse(eventJson);
    } catch {
      event = {};
    }
    setActiveTab('test');
    const result = await invokeFn.mutateAsync({
      id: selectedId,
      body: { event },
    });
    setLastResult(result.data);
  }, [selectedId, eventJson, invokeFn]);

  const handleCreate = useCallback(async (name: string, description: string, source: string, tags: string[]) => {
    const result = await createFn.mutateAsync({ name, description, source, tags });
    setSelectedId(result.data.id);
    setShowCreate(false);
    setSelectedTemplate(null);
    setIsDirty(false);
    setEditedSource(null);
  }, [createFn]);

  const handleDelete = useCallback(async () => {
    if (!selectedId) return;
    await deleteFn.mutateAsync(selectedId);
    setSelectedId(null);
    setShowDeleteConfirm(false);
    setEditedSource(null);
    setIsDirty(false);
  }, [selectedId, deleteFn]);

  const handleConfigChange = useCallback((key: string, value: unknown) => {
    if (!selectedId || !detail) return;
    const newConfig = { ...detail.config, [key]: value };
    updateFn.mutate({ id: selectedId, body: { config: newConfig } });
  }, [selectedId, detail, updateFn]);

  const handleTemplateSelect = (template: FunctionTemplate) => {
    setSelectedTemplate(template);
    setShowCreate(true);
  };

  const tabs: { id: DetailTab; label: string; icon: LucideIcon }[] = [
    { id: 'code', label: 'Code', icon: FileCode2 },
    { id: 'test', label: 'Test', icon: Play },
    { id: 'config', label: 'Configuration', icon: Settings2 },
    { id: 'history', label: 'Invocations', icon: Activity },
  ];

  return (
    <div className="h-full flex flex-col -m-6">
      {/* Top bar */}
      <div className="px-6 pt-6 pb-4 bg-white border-b border-gray-200">
        <PageHeader
          title="Functions"
          description="Create, edit, and execute serverless-style Python functions"
          badge={
            <span className="text-xs px-2 py-0.5 rounded-full bg-spine-50 text-spine-600 border border-spine-200 font-medium">
              {functions.length} functions
            </span>
          }
          actions={
            <div className="flex items-center gap-2">
              <Button variant="secondary" onClick={() => setShowTemplates(true)}>
                <Layers className="w-4 h-4 mr-1.5" />
                Templates
              </Button>
              <Button onClick={() => setShowCreate(true)}>
                <Plus className="w-4 h-4 mr-1.5" />
                Create Function
              </Button>
            </div>
          }
        />
      </div>

      {/* Main content: sidebar + detail */}
      <div className="flex flex-1 min-h-0">
        {/* Left sidebar — function list */}
        <div className="w-72 shrink-0 bg-white border-r border-gray-200 flex flex-col">
          {/* Search */}
          <div className="p-3 border-b border-gray-100">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
              <input
                type="text"
                placeholder="Search functions..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-9 pr-3 py-2 text-xs border border-gray-200 rounded-lg focus:ring-2 focus:ring-spine-500 focus:border-spine-500 bg-gray-50 focus:bg-white transition-colors"
              />
            </div>
          </div>

          {/* Function list */}
          <div className="flex-1 overflow-y-auto">
            {listLoading ? (
              <Spinner />
            ) : listError ? (
              <div className="p-4"><ErrorBox message="Failed to load functions" /></div>
            ) : functions.length === 0 ? (
              <EmptyState message="No functions yet" />
            ) : (
              functions.map((fn) => (
                <FunctionListItem
                  key={fn.id}
                  fn={fn}
                  isSelected={fn.id === selectedId}
                  onSelect={() => {
                    setSelectedId(fn.id);
                    setIsDirty(false);
                    setEditedSource(null);
                    setLastResult(null);
                  }}
                />
              ))
            )}
          </div>
        </div>

        {/* Right detail area */}
        <div className="flex-1 flex flex-col min-w-0 bg-gray-50">
          {!selectedId || !detail ? (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <Zap className="w-12 h-12 text-gray-300 mx-auto mb-3" />
                <p className="text-sm text-gray-500">Select a function or create a new one</p>
              </div>
            </div>
          ) : detailLoading ? (
            <Spinner />
          ) : (
            <>
              {/* Function header */}
              <div className="px-6 py-4 bg-white border-b border-gray-200">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-spine-400 to-spine-600 flex items-center justify-center">
                      <Zap className="w-5 h-5 text-white" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <h2 className="text-lg font-semibold text-gray-900">{detail.name}</h2>
                        <FnStatusBadge status={detail.status} />
                        {isDirty && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-yellow-50 text-yellow-700 border border-yellow-200">
                            unsaved
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-gray-500">{detail.description || 'No description'}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="flex items-center gap-1.5 mr-3 text-xs text-gray-500">
                      <Clock className="w-3.5 h-3.5" />{detail.config.timeout}s
                      <span className="text-gray-300">|</span>
                      <Cpu className="w-3.5 h-3.5" />{detail.config.memory_mb}MB
                      <span className="text-gray-300">|</span>
                      {detail.config.runtime}
                    </div>
                    {isDirty && (
                      <Button onClick={handleSave} disabled={updateFn.isPending}>
                        <Save className="w-4 h-4 mr-1" />
                        {updateFn.isPending ? 'Saving...' : 'Save'}
                      </Button>
                    )}
                    <Button variant="primary" onClick={handleInvoke} disabled={invokeFn.isPending}>
                      <Play className="w-4 h-4 mr-1" />
                      {invokeFn.isPending ? 'Running...' : 'Test'}
                    </Button>
                    <Button variant="danger" size="xs" onClick={() => setShowDeleteConfirm(true)}>
                      <Trash2 className="w-3.5 h-3.5" />
                    </Button>
                  </div>
                </div>

                {/* Tags */}
                {detail.tags.length > 0 && (
                  <div className="flex items-center gap-1.5 mt-2">
                    {detail.tags.map((tag) => (
                      <TagPill key={tag} tag={tag} onClick={() => setSearchQuery(tag)} />
                    ))}
                  </div>
                )}
              </div>

              {/* Tab bar */}
              <div className="px-6 bg-white border-b border-gray-200">
                <div className="flex gap-0">
                  {tabs.map((tab) => (
                    <button
                      key={tab.id}
                      onClick={() => setActiveTab(tab.id)}
                      className={`flex items-center gap-1.5 px-4 py-2.5 text-xs font-medium border-b-2 transition-colors ${
                        activeTab === tab.id
                          ? 'border-spine-500 text-spine-700'
                          : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                      }`}
                    >
                      <tab.icon className="w-3.5 h-3.5" />
                      {tab.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Tab content */}
              <div className="flex-1 overflow-y-auto p-6">
                {activeTab === 'code' && (
                  <div className="space-y-4">
                    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm">
                      <div className="px-4 py-2.5 bg-gray-50 border-b border-gray-200 flex items-center justify-between">
                        <div className="flex items-center gap-2 text-xs text-gray-500">
                          <FileCode2 className="w-3.5 h-3.5" />
                          {detail.name}.py
                          <span className="text-gray-400">&middot;</span>
                          <span>{detail.source.split('\n').length} lines</span>
                        </div>
                        <span className="text-[10px] text-gray-400">
                          Modified {new Date(detail.last_modified).toLocaleString()}
                        </span>
                      </div>
                      <CodeEditor
                        value={editedSource ?? detail.source}
                        onChange={(v) => {
                          setEditedSource(v ?? '');
                          setIsDirty(true);
                        }}
                        language="python"
                        height="450px"
                      />
                    </div>
                  </div>
                )}

                {activeTab === 'test' && (
                  <div className="space-y-4">
                    {/* Event JSON editor */}
                    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm">
                      <div className="px-4 py-2.5 bg-gray-50 border-b border-gray-200 flex items-center justify-between">
                        <div className="flex items-center gap-2 text-xs text-gray-500">
                          <Terminal className="w-3.5 h-3.5" />
                          Test Event (JSON)
                        </div>
                        <Button size="xs" onClick={handleInvoke} disabled={invokeFn.isPending}>
                          <Play className="w-3 h-3 mr-1" />
                          {invokeFn.isPending ? 'Running...' : 'Test'}
                        </Button>
                      </div>
                      <CodeEditor
                        value={eventJson}
                        onChange={(v) => setEventJson(v ?? '{}')}
                        language="json"
                        height="150px"
                      />
                    </div>

                    {/* Result */}
                    {lastResult && (
                      <div className="space-y-3">
                        {/* Status Summary */}
                        <div className={`rounded-xl border p-4 ${
                          lastResult.status === 'success'
                            ? 'bg-emerald-50 border-emerald-200'
                            : lastResult.status === 'timeout'
                            ? 'bg-yellow-50 border-yellow-200'
                            : 'bg-red-50 border-red-200'
                        }`}>
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                              {lastResult.status === 'success' ? (
                                <CheckCircle2 className="w-5 h-5 text-emerald-600" />
                              ) : lastResult.status === 'timeout' ? (
                                <AlertTriangle className="w-5 h-5 text-yellow-600" />
                              ) : (
                                <XCircle className="w-5 h-5 text-red-600" />
                              )}
                              <span className="text-sm font-semibold capitalize">{lastResult.status}</span>
                            </div>
                            <div className="flex items-center gap-4 text-xs text-gray-600">
                              <span>Duration: <strong>{lastResult.duration_ms.toFixed(1)} ms</strong></span>
                              <span>Billed: <strong>{lastResult.billed_duration_ms.toFixed(0)} ms</strong></span>
                              <span className="font-mono text-[10px] text-gray-400">{lastResult.request_id}</span>
                            </div>
                          </div>
                          {lastResult.error && (
                            <p className="mt-2 text-xs text-red-700">
                              <strong>{lastResult.error_type}:</strong> {lastResult.error}
                            </p>
                          )}
                        </div>

                        {/* Return value */}
                        {lastResult.result != null && (
                          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm">
                            <div className="px-4 py-2.5 bg-gray-50 border-b border-gray-200">
                              <span className="text-xs text-gray-500 font-medium">Response</span>
                            </div>
                            <pre className="p-4 text-xs font-mono text-gray-800 overflow-x-auto max-h-48 overflow-y-auto bg-gray-50/50">
                              {JSON.stringify(lastResult.result, null, 2)}
                            </pre>
                          </div>
                        )}

                        {/* Logs */}
                        <LogViewer logs={lastResult.logs} isLoading={invokeFn.isPending} />
                      </div>
                    )}

                    {!lastResult && !invokeFn.isPending && (
                      <div className="text-center py-12 text-gray-400">
                        <Play className="w-10 h-10 mx-auto mb-3 text-gray-300" />
                        <p className="text-sm">Configure a test event above and click <strong>Test</strong></p>
                        <p className="text-xs mt-1">The function will execute locally via subprocess</p>
                      </div>
                    )}
                  </div>
                )}

                {activeTab === 'config' && (
                  <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
                    <h3 className="text-sm font-semibold text-gray-900 mb-4 flex items-center gap-2">
                      <Settings2 className="w-4 h-4 text-spine-500" />
                      General Configuration
                    </h3>
                    <ConfigPanel
                      config={detail.config}
                      onChange={handleConfigChange}
                    />
                    <div className="mt-6 pt-4 border-t border-gray-100">
                      <h4 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-3">Function Info</h4>
                      <div className="grid grid-cols-2 gap-3 text-xs">
                        <div><span className="text-gray-500">ID:</span> <span className="font-mono">{detail.id}</span></div>
                        <div><span className="text-gray-500">Created:</span> {new Date(detail.created_at).toLocaleString()}</div>
                        <div><span className="text-gray-500">Last Modified:</span> {new Date(detail.last_modified).toLocaleString()}</div>
                        <div><span className="text-gray-500">Invocations:</span> {detail.invoke_count}</div>
                        <div><span className="text-gray-500">Last Invoked:</span> {detail.last_invoked ? new Date(detail.last_invoked).toLocaleString() : 'Never'}</div>
                      </div>
                    </div>
                  </div>
                )}

                {activeTab === 'history' && (
                  <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
                    <div className="px-4 py-3 bg-gray-50 border-b border-gray-200">
                      <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Recent Invocations
                      </span>
                    </div>
                    <InvocationHistory functionId={detail.id} />
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>

      {/* Modals */}
      {showTemplates && (
        <TemplateGallery onSelect={handleTemplateSelect} onClose={() => setShowTemplates(false)} />
      )}
      {showCreate && (
        <CreateFunctionModal
          onClose={() => { setShowCreate(false); setSelectedTemplate(null); }}
          onCreate={handleCreate}
          template={selectedTemplate}
        />
      )}
      {showDeleteConfirm && detail && (
        <Modal title="Delete Function" onClose={() => setShowDeleteConfirm(false)}>
          <p className="text-sm text-gray-700 mb-4">
            Are you sure you want to delete <strong>{detail.name}</strong>? This action cannot be undone.
          </p>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setShowDeleteConfirm(false)}>Cancel</Button>
            <Button variant="danger" onClick={handleDelete} disabled={deleteFn.isPending}>
              <Trash2 className="w-4 h-4 mr-1" />
              {deleteFn.isPending ? 'Deleting...' : 'Delete'}
            </Button>
          </div>
        </Modal>
      )}
    </div>
  );
}
