import { useState } from 'react';
import {
  Database as DatabaseIcon,
  HardDrive,
  Table2,
  Terminal,
  RefreshCw,
  Download,
  Trash2,
  Activity,
  ChevronDown,
  ChevronRight,
  Play,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Server,
  FileText,
  Layers,
} from 'lucide-react';
import PageHeader from '../components/PageHeader';
import { Button, Spinner, ErrorBox, Modal } from '../components/UI';
import {
  useDatabaseHealth,
  useDatabaseConfig,
  useDatabaseSchema,
  useTableCounts,
  useRunQuery,
  useVacuum,
  useBackup,
  useInitDatabase,
  usePurgeData,
} from '../api/hooks';
import type { TableSchema } from '../types/api';

// ── Status indicator ───────────────────────────────────────────────

function ConnectionStatus({ connected, backend, latency }: { connected: boolean; backend: string; latency: number }) {
  return (
    <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium ${
      connected ? 'bg-green-50 text-green-700 border border-green-200' : 'bg-red-50 text-red-700 border border-red-200'
    }`}>
      <span className={`w-2 h-2 rounded-full ${connected ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`} />
      {connected ? `${backend} · ${latency.toFixed(1)}ms` : 'Disconnected'}
    </div>
  );
}

// ── Config card ────────────────────────────────────────────────────

function ConfigCard({ label, value, icon: Icon, className = '' }: {
  label: string; value: string | number | null; icon: typeof Server; className?: string;
}) {
  return (
    <div className={`bg-white rounded-xl border border-gray-200/80 p-4 ${className}`}>
      <div className="flex items-center gap-2 text-xs text-gray-500 mb-1.5">
        <Icon className="w-3.5 h-3.5" />
        {label}
      </div>
      <div className="text-sm font-semibold text-gray-900 truncate" title={String(value ?? '—')}>
        {value ?? '—'}
      </div>
    </div>
  );
}

// ── Table schema explorer ──────────────────────────────────────────

function TableExplorer({ tables }: { tables: TableSchema[] }) {
  const [expanded, setExpanded] = useState<string | null>(null);

  return (
    <div className="divide-y divide-gray-100">
      {tables.map((t) => (
        <div key={t.table_name}>
          <button
            className="w-full flex items-center gap-3 px-4 py-3 hover:bg-gray-50 transition-colors text-left"
            onClick={() => setExpanded(expanded === t.table_name ? null : t.table_name)}
          >
            {expanded === t.table_name ? (
              <ChevronDown className="w-4 h-4 text-gray-400 shrink-0" />
            ) : (
              <ChevronRight className="w-4 h-4 text-gray-400 shrink-0" />
            )}
            <Table2 className="w-4 h-4 text-spine-500 shrink-0" />
            <span className="font-mono text-sm font-medium text-gray-900 flex-1">{t.table_name}</span>
            <span className="text-xs text-gray-500 tabular-nums">{t.row_count.toLocaleString()} rows</span>
            <span className="text-xs text-gray-400">{t.columns.length} cols</span>
          </button>

          {expanded === t.table_name && (
            <div className="px-4 pb-3 ml-11">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-gray-500 border-b border-gray-100">
                    <th className="pb-1 pr-4 font-medium">Column</th>
                    <th className="pb-1 pr-4 font-medium">Type</th>
                    <th className="pb-1 pr-4 font-medium">Nullable</th>
                    <th className="pb-1 pr-4 font-medium">PK</th>
                    <th className="pb-1 font-medium">Default</th>
                  </tr>
                </thead>
                <tbody>
                  {t.columns.map((col) => (
                    <tr key={col.name} className="border-b border-gray-50">
                      <td className="py-1 pr-4 font-mono text-gray-900">{col.name}</td>
                      <td className="py-1 pr-4 text-purple-600 font-mono">{col.type}</td>
                      <td className="py-1 pr-4">{col.nullable ? '✓' : '—'}</td>
                      <td className="py-1 pr-4">{col.primary_key ? '🔑' : '—'}</td>
                      <td className="py-1 text-gray-500 font-mono">{col.default ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {t.indexes.length > 0 && (
                <div className="mt-2 flex items-center gap-2 flex-wrap">
                  <span className="text-[10px] uppercase tracking-wider text-gray-400 font-semibold">Indexes:</span>
                  {t.indexes.map((idx) => (
                    <span key={idx} className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded font-mono">{idx}</span>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ── SQL Query Console ──────────────────────────────────────────────

function QueryConsole() {
  const runQuery = useRunQuery();
  const [sql, setSql] = useState('SELECT name FROM sqlite_master WHERE type=\'table\' ORDER BY name');
  const [limit, setLimit] = useState(100);

  const result = runQuery.data?.data;

  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        <textarea
          value={sql}
          onChange={(e) => setSql(e.target.value)}
          rows={3}
          className="flex-1 font-mono text-sm border border-gray-200 rounded-lg px-3 py-2 focus:ring-2 focus:ring-spine-500/20 focus:border-spine-500 resize-y"
          placeholder="SELECT * FROM core_executions LIMIT 10"
        />
      </div>
      <div className="flex items-center gap-3">
        <Button
          onClick={() => runQuery.mutate({ sql, limit })}
          disabled={runQuery.isPending || !sql.trim()}
        >
          {runQuery.isPending ? <Spinner /> : <><Play className="w-3.5 h-3.5 mr-1.5" />Run Query</>}
        </Button>
        <div className="flex items-center gap-1.5 text-xs text-gray-500">
          <span>Limit:</span>
          <select
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
            className="border rounded px-2 py-1 text-xs"
          >
            <option value={10}>10</option>
            <option value={50}>50</option>
            <option value={100}>100</option>
            <option value={500}>500</option>
            <option value={1000}>1000</option>
          </select>
        </div>
        {result && (
          <span className="text-xs text-gray-500">
            {result.row_count} rows · {result.elapsed_ms.toFixed(1)}ms
            {result.truncated && ' (truncated)'}
          </span>
        )}
      </div>

      {runQuery.isError && (
        <div className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2 border border-red-200">
          {runQuery.error instanceof Error ? runQuery.error.message : 'Query failed'}
        </div>
      )}

      {result && result.columns.length > 0 && (
        <div className="overflow-x-auto border border-gray-200 rounded-lg">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                {result.columns.map((col) => (
                  <th key={col} className="text-left px-3 py-2 font-semibold text-gray-700 font-mono whitespace-nowrap">
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {result.rows.map((row, i) => (
                <tr key={i} className="hover:bg-gray-50">
                  {row.map((cell, j) => (
                    <td key={j} className="px-3 py-1.5 font-mono text-gray-700 max-w-[300px] truncate whitespace-nowrap">
                      {cell === null ? <span className="text-gray-400 italic">NULL</span> : String(cell)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Table counts bar chart ─────────────────────────────────────────

function TableCountsChart({ data }: { data: { table: string; count: number }[] }) {
  const maxCount = Math.max(...data.map((d) => d.count), 1);

  return (
    <div className="space-y-1.5">
      {data.map((d) => (
        <div key={d.table} className="flex items-center gap-3">
          <span className="w-40 text-xs font-mono text-gray-700 truncate shrink-0" title={d.table}>
            {d.table}
          </span>
          <div className="flex-1 h-5 bg-gray-100 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-spine-400 to-spine-600 rounded-full transition-all duration-500"
              style={{ width: `${Math.max((d.count / maxCount) * 100, 1)}%` }}
            />
          </div>
          <span className="text-xs tabular-nums text-gray-500 w-16 text-right shrink-0">
            {d.count.toLocaleString()}
          </span>
        </div>
      ))}
    </div>
  );
}

// ── Main Page ──────────────────────────────────────────────────────

export default function DatabasePage() {
  const health = useDatabaseHealth();
  const config = useDatabaseConfig();
  const schema = useDatabaseSchema();
  const tableCounts = useTableCounts();
  const vacuum = useVacuum();
  const backup = useBackup();
  const initDb = useInitDatabase();
  const purge = usePurgeData();

  const [activeTab, setActiveTab] = useState<'overview' | 'schema' | 'query' | 'maintenance'>('overview');
  const [showPurgeModal, setShowPurgeModal] = useState(false);
  const [purgeDays, setPurgeDays] = useState(90);

  const healthData = health.data?.data;
  const configData = config.data?.data;
  const schemaData = schema.data?.data;
  const tableData = tableCounts.data?.data;

  const tabs = [
    { id: 'overview' as const, label: 'Overview', icon: Activity },
    { id: 'schema' as const, label: 'Schema Browser', icon: Layers },
    { id: 'query' as const, label: 'Query Console', icon: Terminal },
    { id: 'maintenance' as const, label: 'Maintenance', icon: HardDrive },
  ];

  return (
    <>
      <PageHeader
        title="Database"
        description="Manage and inspect spine-core database — schema, queries, backups"
      />

      {/* Connection banner */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          {healthData && (
            <ConnectionStatus
              connected={healthData.connected}
              backend={healthData.backend}
              latency={healthData.latency_ms}
            />
          )}
          {configData && (
            <span className="text-xs text-gray-500 bg-gray-100 px-2.5 py-1 rounded-full">
              Tier: <span className="font-semibold">{configData.tier}</span>
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" size="sm" onClick={() => { health.refetch(); config.refetch(); schema.refetch(); tableCounts.refetch(); }}>
            <RefreshCw className="w-3.5 h-3.5 mr-1.5" />Refresh
          </Button>
        </div>
      </div>

      {/* Config cards */}
      {configData && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
          <ConfigCard label="Backend" value={configData.backend} icon={Server} />
          <ConfigCard label="Connection" value={configData.url_masked} icon={DatabaseIcon} />
          <ConfigCard label="Data Directory" value={configData.data_dir} icon={FileText} />
          <ConfigCard
            label="DB Size"
            value={configData.file_size_mb ? `${configData.file_size_mb} MB` : configData.is_persistent ? 'N/A (remote)' : 'In-Memory'}
            icon={HardDrive}
          />
        </div>
      )}

      {/* Tab bar */}
      <div className="flex items-center gap-1 border-b border-gray-200 mb-6">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
              activeTab === tab.id
                ? 'border-spine-500 text-spine-700'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            <tab.icon className="w-4 h-4" />
            {tab.label}
          </button>
        ))}
      </div>

      {health.isLoading && <Spinner />}
      {health.isError && (
        <ErrorBox
          message="Cannot connect to database"
          detail={health.error instanceof Error ? health.error.message : undefined}
          onRetry={() => health.refetch()}
        />
      )}

      {/* Overview Tab */}
      {activeTab === 'overview' && (
        <div className="space-y-6">
          {/* Health metrics */}
          {healthData && (
            <div className="bg-white rounded-xl border border-gray-200/80 p-5">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-4">Health Metrics</h3>
              <div className="grid grid-cols-4 gap-4">
                <div className="text-center">
                  {healthData.connected ? (
                    <CheckCircle2 className="w-8 h-8 text-green-500 mx-auto mb-1" />
                  ) : (
                    <XCircle className="w-8 h-8 text-red-500 mx-auto mb-1" />
                  )}
                  <p className="text-xs text-gray-500">Status</p>
                  <p className="text-sm font-semibold">{healthData.connected ? 'Connected' : 'Disconnected'}</p>
                </div>
                <div className="text-center">
                  <p className="text-2xl font-bold text-spine-600">{healthData.latency_ms.toFixed(1)}</p>
                  <p className="text-xs text-gray-500">Latency (ms)</p>
                </div>
                <div className="text-center">
                  <p className="text-2xl font-bold text-spine-600">{healthData.table_count}</p>
                  <p className="text-xs text-gray-500">Tables</p>
                </div>
                <div className="text-center">
                  <p className="text-2xl font-bold text-spine-600">{healthData.backend}</p>
                  <p className="text-xs text-gray-500">Backend</p>
                </div>
              </div>
            </div>
          )}

          {/* Table counts */}
          {tableData && tableData.length > 0 && (
            <div className="bg-white rounded-xl border border-gray-200/80 p-5">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-4">Table Sizes</h3>
              <TableCountsChart data={tableData} />
            </div>
          )}

          {/* Env/Tier info */}
          {configData && (
            <div className="bg-white rounded-xl border border-gray-200/80 p-5">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-4">Configuration</h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
                <div>
                  <span className="text-gray-500">Active Tier:</span>
                  <span className={`ml-2 font-semibold ${
                    configData.tier === 'full' ? 'text-purple-600' :
                    configData.tier === 'standard' ? 'text-blue-600' : 'text-green-600'
                  }`}>
                    {configData.tier.charAt(0).toUpperCase() + configData.tier.slice(1)}
                  </span>
                </div>
                <div>
                  <span className="text-gray-500">Env File:</span>
                  <span className="ml-2 font-mono text-xs">{configData.env_file_hint}</span>
                </div>
                <div>
                  <span className="text-gray-500">Persistent:</span>
                  <span className="ml-2">{configData.is_persistent ? '✅ Yes' : '⚠️ In-Memory'}</span>
                </div>
              </div>

              {/* Quick start commands */}
              <div className="mt-4 pt-4 border-t border-gray-100">
                <h4 className="text-xs font-semibold text-gray-500 mb-2">Quick Switch</h4>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-2 text-xs">
                  <div className="bg-gray-50 rounded-lg p-3 font-mono">
                    <span className="text-green-600 font-semibold">Minimal</span>
                    <br />docker compose up
                  </div>
                  <div className="bg-gray-50 rounded-lg p-3 font-mono">
                    <span className="text-blue-600 font-semibold">Standard</span>
                    <br />docker compose --profile standard up
                  </div>
                  <div className="bg-gray-50 rounded-lg p-3 font-mono">
                    <span className="text-purple-600 font-semibold">Full</span>
                    <br />docker compose --profile full up
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Schema Tab */}
      {activeTab === 'schema' && (
        <div className="bg-white rounded-xl border border-gray-200/80 overflow-hidden">
          <div className="px-5 py-3 border-b border-gray-100 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-gray-900">
              Tables ({schemaData?.length ?? 0})
            </h3>
            <Button variant="secondary" size="xs" onClick={() => schema.refetch()}>
              <RefreshCw className="w-3 h-3 mr-1" />Refresh
            </Button>
          </div>
          {schema.isLoading && <div className="p-8"><Spinner /></div>}
          {schemaData && schemaData.length > 0 ? (
            <TableExplorer tables={schemaData} />
          ) : (
            <div className="p-8 text-center text-gray-500 text-sm">
              No tables found. Click <strong>Init Database</strong> in Maintenance to create schema.
            </div>
          )}
        </div>
      )}

      {/* Query Tab */}
      {activeTab === 'query' && (
        <div className="bg-white rounded-xl border border-gray-200/80 p-5">
          <div className="flex items-center gap-2 mb-4">
            <Terminal className="w-4 h-4 text-spine-500" />
            <h3 className="text-sm font-semibold text-gray-900">SQL Query Console</h3>
            <span className="text-xs text-gray-400 ml-2">Read-only SELECT queries only</span>
          </div>
          <QueryConsole />
        </div>
      )}

      {/* Maintenance Tab */}
      {activeTab === 'maintenance' && (
        <div className="space-y-4">
          {/* Init schema */}
          <div className="bg-white rounded-xl border border-gray-200/80 p-5">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-semibold text-gray-900">Initialize Schema</h3>
                <p className="text-xs text-gray-500 mt-1">Create all spine-core tables (safe — uses CREATE TABLE IF NOT EXISTS).</p>
              </div>
              <div className="flex gap-2">
                <Button variant="secondary" size="sm" onClick={() => initDb.mutate(true)}>
                  Dry Run
                </Button>
                <Button size="sm" onClick={() => initDb.mutate(false)}>
                  <DatabaseIcon className="w-3.5 h-3.5 mr-1.5" />Init
                </Button>
              </div>
            </div>
            {initDb.isSuccess && (
              <div className="mt-3 text-xs text-green-700 bg-green-50 rounded-lg p-2">
                ✅ Schema initialized successfully
              </div>
            )}
          </div>

          {/* VACUUM */}
          <div className="bg-white rounded-xl border border-gray-200/80 p-5">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-semibold text-gray-900">Vacuum Database</h3>
                <p className="text-xs text-gray-500 mt-1">Reclaim unused space and defragment (SQLite only).</p>
              </div>
              <Button size="sm" onClick={() => vacuum.mutate()} disabled={vacuum.isPending}>
                {vacuum.isPending ? <Spinner /> : <><HardDrive className="w-3.5 h-3.5 mr-1.5" />Vacuum</>}
              </Button>
            </div>
            {vacuum.isSuccess && vacuum.data?.data && (
              <div className={`mt-3 text-xs rounded-lg p-2 ${
                vacuum.data.data.success ? 'text-green-700 bg-green-50' : 'text-amber-700 bg-amber-50'
              }`}>
                {vacuum.data.data.message}
              </div>
            )}
          </div>

          {/* Backup */}
          <div className="bg-white rounded-xl border border-gray-200/80 p-5">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-semibold text-gray-900">Backup Database</h3>
                <p className="text-xs text-gray-500 mt-1">Create a timestamped copy of the database file (SQLite only).</p>
              </div>
              <Button size="sm" onClick={() => backup.mutate()} disabled={backup.isPending}>
                {backup.isPending ? <Spinner /> : <><Download className="w-3.5 h-3.5 mr-1.5" />Backup</>}
              </Button>
            </div>
            {backup.isSuccess && backup.data?.data && (
              <div className={`mt-3 text-xs rounded-lg p-2 ${
                backup.data.data.success ? 'text-green-700 bg-green-50' : 'text-amber-700 bg-amber-50'
              }`}>
                {backup.data.data.message}
                {backup.data.data.size_mb != null && ` (${backup.data.data.size_mb} MB)`}
              </div>
            )}
          </div>

          {/* Purge */}
          <div className="bg-white rounded-xl border border-gray-200/80 p-5">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-semibold text-gray-900 flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 text-amber-500" />
                  Purge Old Data
                </h3>
                <p className="text-xs text-gray-500 mt-1">Delete execution records older than N days. Irreversible — preview with dry run first.</p>
              </div>
              <Button variant="secondary" size="sm" onClick={() => setShowPurgeModal(true)}>
                <Trash2 className="w-3.5 h-3.5 mr-1.5" />Purge…
              </Button>
            </div>
          </div>

          {/* Env files reference */}
          <div className="bg-white rounded-xl border border-gray-200/80 p-5">
            <h3 className="text-sm font-semibold text-gray-900 mb-3">Environment Files</h3>
            <div className="space-y-2 text-xs font-mono">
              {[
                { file: '.env.minimal', desc: 'SQLite — zero config, embedded', tier: 'minimal' },
                { file: '.env.standard', desc: 'PostgreSQL 16 — docker compose --profile standard', tier: 'standard' },
                { file: '.env.full', desc: 'TimescaleDB + Redis + Celery + Prometheus', tier: 'full' },
                { file: '.env.local.example', desc: 'Local dev overrides (copy to .env.local)', tier: 'dev' },
              ].map((f) => (
                <div key={f.file} className="flex items-center gap-3 bg-gray-50 rounded-lg p-2.5">
                  <FileText className="w-3.5 h-3.5 text-gray-400 shrink-0" />
                  <span className="text-gray-900 font-semibold">{f.file}</span>
                  <span className="text-gray-500 flex-1">{f.desc}</span>
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-sans font-semibold ${
                    f.tier === 'full' ? 'bg-purple-100 text-purple-700' :
                    f.tier === 'standard' ? 'bg-blue-100 text-blue-700' :
                    f.tier === 'minimal' ? 'bg-green-100 text-green-700' :
                    'bg-gray-100 text-gray-600'
                  }`}>
                    {f.tier}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Purge Modal */}
      {showPurgeModal && (
        <Modal title="Purge Old Data" onClose={() => setShowPurgeModal(false)}>
          <div className="space-y-4">
            <p className="text-sm text-gray-600">
              This will permanently delete execution records older than the specified number of days.
            </p>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Delete records older than (days)
              </label>
              <input
                type="number"
                value={purgeDays}
                onChange={(e) => setPurgeDays(Number(e.target.value))}
                min={1}
                className="w-full border rounded-lg px-3 py-2 text-sm"
              />
            </div>
            {purge.isSuccess && (
              <div className="text-xs text-green-700 bg-green-50 rounded-lg p-2">
                ✅ Purge complete
              </div>
            )}
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="secondary" onClick={() => setShowPurgeModal(false)}>Cancel</Button>
              <Button variant="secondary" onClick={() => purge.mutate({ older_than_days: purgeDays, dry_run: true })}>
                {purge.isPending ? <Spinner /> : 'Preview (Dry Run)'}
              </Button>
              <Button onClick={() => { if (confirm('This cannot be undone. Continue?')) purge.mutate({ older_than_days: purgeDays, dry_run: false }); }}>
                <Trash2 className="w-3.5 h-3.5 mr-1.5" />Purge
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}
