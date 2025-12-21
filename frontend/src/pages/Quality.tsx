import { useState } from 'react';
import PageHeader from '../components/PageHeader';
import StatusBadge from '../components/StatusBadge';
import { Spinner, ErrorBox, EmptyState } from '../components/UI';
import { useQuality, useAnomalies } from '../api/hooks';

export default function Quality() {
  const [pipelineFilter, setPipelineFilter] = useState('');
  const quality = useQuality({ pipeline: pipelineFilter || undefined, limit: 50 });
  const anomalies = useAnomalies({ pipeline: pipelineFilter || undefined, limit: 50 });

  // Derive pipeline list from quality data
  const pipelines = [...new Set(
    [...(quality.data?.data ?? []), ...(anomalies.data?.data ?? [])]
      .map((d) => d.pipeline)
      .filter(Boolean),
  )];

  return (
    <>
      <PageHeader
        title="Quality & Anomalies"
        description="Data quality checks and anomaly detection results"
      />

      {/* Pipeline filter */}
      {pipelines.length > 1 && (
        <div className="flex gap-2 mb-4">
          <select
            value={pipelineFilter}
            onChange={(e) => setPipelineFilter(e.target.value)}
            className="text-xs border rounded px-2 py-1.5 bg-white"
          >
            <option value="">All Pipelines</option>
            {pipelines.map((p) => (
              <option key={p} value={p!}>{p}</option>
            ))}
          </select>
        </div>
      )}

      {/* Quality results */}
      <div className="mb-8">
        <h3 className="text-lg font-semibold text-gray-800 mb-3">
          Quality Results
        </h3>
        {quality.isLoading && <Spinner />}
        {quality.isError && (
          <ErrorBox
            message="Failed to load quality results"
            detail={quality.error instanceof Error ? quality.error.message : undefined}
            onRetry={() => quality.refetch()}
          />
        )}
        {quality.data?.data?.length === 0 && (
          <EmptyState message="No quality results yet" />
        )}
        {quality.data?.data && quality.data.data.length > 0 && (
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-left text-xs text-gray-500">
                <tr>
                  <th className="px-4 py-3">Pipeline</th>
                  <th className="px-4 py-3">Passed</th>
                  <th className="px-4 py-3">Failed</th>
                  <th className="px-4 py-3">Score</th>
                  <th className="px-4 py-3">Run At</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {quality.data.data.map((q, i) => (
                  <tr key={i} className="hover:bg-gray-50">
                    <td className="px-4 py-3">{q.pipeline || '—'}</td>
                    <td className="px-4 py-3 text-green-600 font-mono">
                      {q.checks_passed}
                    </td>
                    <td className="px-4 py-3 text-red-600 font-mono">
                      {q.checks_failed}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <div className="w-20 h-2 bg-gray-200 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full ${
                              q.score >= 0.8
                                ? 'bg-green-500'
                                : q.score >= 0.5
                                  ? 'bg-yellow-500'
                                  : 'bg-red-500'
                            }`}
                            style={{ width: `${q.score * 100}%` }}
                          />
                        </div>
                        <span className="text-xs font-mono">
                          {(q.score * 100).toFixed(0)}%
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-500">
                      {q.run_at || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Anomalies */}
      <div>
        <h3 className="text-lg font-semibold text-gray-800 mb-3">Anomalies</h3>
        {anomalies.isLoading && <Spinner />}
        {anomalies.isError && (
          <ErrorBox message="Failed to load anomalies" />
        )}
        {anomalies.data?.data?.length === 0 && (
          <EmptyState message="No anomalies detected — looking good!" />
        )}
        {anomalies.data?.data && anomalies.data.data.length > 0 && (
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-left text-xs text-gray-500">
                <tr>
                  <th className="px-4 py-3">Pipeline</th>
                  <th className="px-4 py-3">Metric</th>
                  <th className="px-4 py-3">Severity</th>
                  <th className="px-4 py-3">Value</th>
                  <th className="px-4 py-3">Threshold</th>
                  <th className="px-4 py-3">Detected</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {anomalies.data.data.map((a) => (
                  <tr key={a.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3">{a.pipeline || '—'}</td>
                    <td className="px-4 py-3 font-mono text-xs">{a.metric}</td>
                    <td className="px-4 py-3">
                      <StatusBadge status={a.severity} />
                    </td>
                    <td className="px-4 py-3 font-mono">
                      {a.value.toFixed(2)}
                    </td>
                    <td className="px-4 py-3 font-mono text-gray-500">
                      {a.threshold.toFixed(2)}
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-500">
                      {a.detected_at || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
