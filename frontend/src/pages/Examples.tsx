import { useState } from 'react';
import { Play, Filter, ChevronDown, ChevronRight, Loader2, Beaker, Code2, FileText } from 'lucide-react';
import PageHeader from '../components/PageHeader';
import StatusBadge from '../components/StatusBadge';
import CodeEditor from '../components/CodeEditor';
import { Card, Spinner, ErrorBox, EmptyState } from '../components/UI';
import {
  useExamples,
  useExampleCategories,
  useExampleResults,
  useExampleRunStatus,
  useRunExamples,
  useExampleSource,
} from '../api/hooks';

// ── Source Code Viewer sub-component ────────────────────────────────
function ExampleSourceViewer({ name }: { name: string }) {
  const sourceQ = useExampleSource(name);

  if (sourceQ.isLoading) {
    return (
      <div className="flex items-center justify-center py-6 text-gray-400 text-xs gap-2">
        <Loader2 className="w-3.5 h-3.5 animate-spin" />
        Loading source code…
      </div>
    );
  }
  if (sourceQ.isError) {
    return (
      <div className="p-3 text-xs text-red-600 bg-red-50 rounded-lg">
        Failed to load source: {sourceQ.error instanceof Error ? sourceQ.error.message : 'Unknown error'}
      </div>
    );
  }

  const src = sourceQ.data?.data;
  if (!src) return null;

  return (
    <div className="space-y-2">
      {src.description && (
        <p className="text-xs text-gray-500 italic px-1">{src.description}</p>
      )}
      <CodeEditor
        value={src.source}
        language="python"
        height={`${Math.min(Math.max(src.line_count * 19, 120), 500)}px`}
        readOnly
        fileName={src.path}
        showToolbar
        theme="dark"
        minimap={src.line_count > 60}
      />
    </div>
  );
}

export default function Examples() {
  const [categoryFilter, setCategoryFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [expandedRow, setExpandedRow] = useState<string | null>(null);
  const [expandedView, setExpandedView] = useState<'output' | 'source'>('source');

  const examples = useExamples({
    category: categoryFilter || undefined,
    limit: 500,
  });
  const categories = useExampleCategories();
  const results = useExampleResults();
  const runStatus = useExampleRunStatus();
  const runExamples = useRunExamples();

  const summary = results.data?.data;
  const isRunning = runStatus.data?.data?.status === 'running';

  // Merge registry data with results for the combined view
  const resultMap = new Map(
    (summary?.examples ?? []).map((r) => [r.name, r]),
  );

  // Build display rows: prefer results when available, fall back to registry
  const displayRows = summary?.examples?.length
    ? summary.examples
        .filter((r) => !categoryFilter || r.category === categoryFilter)
        .filter((r) => !statusFilter || r.status === statusFilter)
    : [];

  const categoryList = categories.data?.data ?? summary?.categories ?? [];

  return (
    <>
      <PageHeader
        title="Examples"
        description="Browse and run 144 spine-core examples — click any row to view source code in Monaco"
        actions={
          <div className="flex gap-2">
            {categoryFilter && (
              <button
                onClick={() => runExamples.mutate({ category: categoryFilter })}
                disabled={isRunning || runExamples.isPending}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-spine-600 text-white hover:bg-spine-700 disabled:opacity-50 transition-colors"
              >
                <Play className="w-3 h-3" />{isRunning ? 'Running…' : `Run ${categoryFilter}`}
              </button>
            )}
            <button
              onClick={() => runExamples.mutate({})}
              disabled={isRunning || runExamples.isPending}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-spine-700 text-white hover:bg-spine-800 disabled:opacity-50 transition-colors"
            >
              <Play className="w-3 h-3" />{isRunning ? 'Running…' : 'Run All'}
            </button>
          </div>
        }
      />

      {/* Summary cards */}
      {summary && summary.total > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <Card title="Total" value={summary.total} color="blue" />
          <Card title="Passed" value={summary.passed} color="green" />
          <Card title="Failed" value={summary.failed} color={summary.failed > 0 ? 'red' : 'green'} />
          <Card
            title="Last Run"
            value={
              summary.last_run_at
                ? new Date(summary.last_run_at).toLocaleDateString()
                : 'Never'
            }
            subtitle={
              summary.last_run_at
                ? new Date(summary.last_run_at).toLocaleTimeString()
                : undefined
            }
            color="gray"
          />
        </div>
      )}

      {/* Run status banner */}
      {isRunning && (
        <div className="flex items-center gap-2 mb-4 px-4 py-2.5 bg-blue-50 border border-blue-200 rounded-xl text-sm text-blue-800">
          <Loader2 className="w-4 h-4 animate-spin" />
          Examples are running… Results will refresh automatically.
        </div>
      )}

      {/* Filters */}
      <div className="flex gap-2 mb-4">
        <div className="relative">
          <Filter className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
          <select
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
            className="text-xs border rounded-lg pl-8 pr-3 py-1.5 bg-white appearance-none"
          >
            <option value="">All Categories</option>
            {categoryList.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>
        {summary && summary.total > 0 && (
          <div className="relative">
            <Filter className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="text-xs border rounded-lg pl-8 pr-3 py-1.5 bg-white appearance-none"
            >
              <option value="">All Statuses</option>
              <option value="PASS">Pass</option>
              <option value="FAIL">Fail</option>
            </select>
          </div>
        )}
      </div>

      {/* Results table (when results exist) */}
      {summary && summary.examples.length > 0 && (
        <div className="mb-8">
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
            Run Results
            <span className="ml-2 font-normal text-gray-400">
              ({displayRows.length} shown)
            </span>
          </h3>
          <div className="bg-white rounded-xl shadow-sm border border-gray-200/80 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50/80 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                <tr>
                  <th className="px-5 py-3 w-8"></th>
                  <th className="px-5 py-3">Name</th>
                  <th className="px-5 py-3">Category</th>
                  <th className="px-5 py-3">Title</th>
                  <th className="px-5 py-3">Status</th>
                  <th className="px-5 py-3 text-right">Duration</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100/80">
                {displayRows.map((r) => (
                  <>
                    <tr
                      key={r.name}
                      className="hover:bg-gray-50/50 cursor-pointer"
                      onClick={() =>
                        setExpandedRow(expandedRow === r.name ? null : r.name)
                      }
                    >
                      <td className="px-5 py-3 text-gray-400 text-xs">
                        {expandedRow === r.name ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                      </td>
                      <td className="px-5 py-3 font-mono text-xs">
                        {r.name.split('/')[1] || r.name}
                      </td>
                      <td className="px-5 py-3 text-xs text-gray-600">
                        {r.category}
                      </td>
                      <td className="px-5 py-3 text-xs">{r.title || '—'}</td>
                      <td className="px-5 py-3">
                        <StatusBadge status={r.status} />
                      </td>
                      <td className="px-5 py-3 text-right font-mono text-xs text-gray-500">
                        {r.duration_seconds.toFixed(1)}s
                      </td>
                    </tr>
                    {expandedRow === r.name && (
                      <tr key={`${r.name}-detail`}>
                        <td colSpan={6} className="px-5 py-4 bg-gray-50/50">
                          {/* Tab toggle: Source / Output */}
                          <div className="flex gap-1 mb-3">
                            <button
                              onClick={(e) => { e.stopPropagation(); setExpandedView('source'); }}
                              className={`inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-md transition-colors ${
                                expandedView === 'source'
                                  ? 'bg-spine-100 text-spine-800'
                                  : 'text-gray-500 hover:bg-gray-100'
                              }`}
                            >
                              <Code2 className="w-3 h-3" />Source Code
                            </button>
                            {r.stdout_tail.length > 0 && (
                              <button
                                onClick={(e) => { e.stopPropagation(); setExpandedView('output'); }}
                                className={`inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-md transition-colors ${
                                  expandedView === 'output'
                                    ? 'bg-spine-100 text-spine-800'
                                    : 'text-gray-500 hover:bg-gray-100'
                                }`}
                              >
                                <FileText className="w-3 h-3" />Output ({r.stdout_tail.length} lines)
                              </button>
                            )}
                          </div>

                          {/* Content */}
                          {expandedView === 'source' ? (
                            <ExampleSourceViewer name={r.name} />
                          ) : (
                            <CodeEditor
                              value={r.stdout_tail.join('\n')}
                              language="plaintext"
                              height={`${Math.min(Math.max(r.stdout_tail.length * 19, 100), 400)}px`}
                              readOnly
                              fileName="stdout"
                              showToolbar
                              theme="dark"
                              minimap={false}
                              lineNumbers={false}
                            />
                          )}
                        </td>
                      </tr>
                    )}
                  </>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Registry list (always shown) */}
      <div>
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3 flex items-center gap-2">
          <Beaker className="w-3.5 h-3.5" />
          Example Registry
          <span className="font-normal text-gray-400">
            ({examples.data?.page?.total ?? '…'} discovered)
          </span>
        </h3>
        {examples.isLoading && <Spinner />}
        {examples.isError && (
          <ErrorBox
            message="Failed to load examples"
            detail={
              examples.error instanceof Error
                ? examples.error.message
                : undefined
            }
            onRetry={() => examples.refetch()}
          />
        )}
        {examples.data?.data?.length === 0 && (
          <EmptyState message="No examples found in the examples/ directory" />
        )}
        {examples.data?.data && examples.data.data.length > 0 && (
          <div className="bg-white rounded-xl shadow-sm border border-gray-200/80 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50/80 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                <tr>
                  <th className="px-5 py-3 w-8"></th>
                  <th className="px-5 py-3">#</th>
                  <th className="px-5 py-3">Category</th>
                  <th className="px-5 py-3">Name</th>
                  <th className="px-5 py-3">Title</th>
                  <th className="px-5 py-3">Result</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100/80">
                {examples.data.data.map((ex) => {
                  const result = resultMap.get(ex.name);
                  const isExpanded = expandedRow === ex.name;
                  return (
                    <>
                      <tr
                        key={ex.name}
                        className="hover:bg-gray-50/50 cursor-pointer transition-colors"
                        onClick={() => setExpandedRow(isExpanded ? null : ex.name)}
                      >
                        <td className="px-5 py-3 text-gray-400 text-xs">
                          {isExpanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                        </td>
                        <td className="px-5 py-3 text-xs text-gray-400 font-mono">
                          {ex.order}
                        </td>
                      <td className="px-5 py-3 text-xs text-gray-600">
                        {ex.category}
                      </td>
                      <td className="px-5 py-3 font-mono text-xs">
                        {ex.name.split('/')[1] || ex.name}
                      </td>
                      <td className="px-5 py-3 text-xs">
                        {ex.title || '—'}
                      </td>
                      <td className="px-5 py-3">
                          {result ? (
                            <StatusBadge status={result.status} />
                          ) : (
                            <span className="text-xs text-gray-400">—</span>
                          )}
                        </td>
                      </tr>
                      {isExpanded && (
                        <tr key={`${ex.name}-source`}>
                          <td colSpan={6} className="px-5 py-4 bg-gray-50/50">
                            <ExampleSourceViewer name={ex.name} />
                          </td>
                        </tr>
                      )}
                    </>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
