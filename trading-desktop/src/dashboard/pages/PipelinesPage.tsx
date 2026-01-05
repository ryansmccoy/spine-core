import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  PlayIcon,
  EyeIcon,
  InformationCircleIcon,
} from '@heroicons/react/24/outline';
import { useState } from 'react';
import { useSpineClient, useCapabilities } from '../../api';
import type { PipelineSummary, ExecutionResponse } from '../../api';

export default function PipelinesPage() {
  const client = useSpineClient();
  const capabilities = useCapabilities();
  const [selectedPipeline, setSelectedPipeline] = useState<string | null>(null);

  const { data: pipelinesResponse, isLoading, error } = useQuery({
    queryKey: ['spine', 'pipelines'],
    queryFn: () => client.listPipelines(),
    refetchInterval: 30000, // Slower refresh since Basic has no async execution
  });

  const pipelines = pipelinesResponse?.pipelines ?? [];

  return (
    <div className="pipelines-page">
      <header className="page-header">
        <h1 className="page-title">Pipelines</h1>
        <div className="page-subtitle">
          {pipelines.length} pipeline{pipelines.length !== 1 ? 's' : ''} available
          {capabilities && !capabilities.hasScheduling && (
            <span className="tier-note"> • Manual execution only (Basic tier)</span>
          )}
        </div>
      </header>

      {error ? (
        <div className="error-state">
          <p>Failed to load pipelines: {error instanceof Error ? error.message : 'Unknown error'}</p>
        </div>
      ) : isLoading ? (
        <div className="loading-state">
          <div className="spinner" />
          Loading pipelines...
        </div>
      ) : (
        <div className="pipeline-table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>Pipeline</th>
                <th>Description</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {pipelines.length > 0 ? (
                pipelines.map((pipeline) => (
                  <PipelineRow 
                    key={pipeline.name} 
                    pipeline={pipeline}
                    onSelect={() => setSelectedPipeline(pipeline.name)}
                    isSelected={selectedPipeline === pipeline.name}
                  />
                ))
              ) : (
                <tr>
                  <td colSpan={3} className="empty-row">
                    No pipelines registered
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Pipeline Detail Panel */}
      {selectedPipeline && (
        <PipelineDetailPanel
          pipelineName={selectedPipeline}
          onClose={() => setSelectedPipeline(null)}
        />
      )}
    </div>
  );
}

interface PipelineRowProps {
  pipeline: PipelineSummary;
  onSelect: () => void;
  isSelected: boolean;
}

function PipelineRow({ pipeline, onSelect, isSelected }: PipelineRowProps) {
  const client = useSpineClient();
  const queryClient = useQueryClient();
  const [executing, setExecuting] = useState(false);
  const [lastResult, setLastResult] = useState<ExecutionResponse | null>(null);
  
  const runMutation = useMutation({
    mutationFn: () => client.runPipeline(pipeline.name),
    onMutate: () => {
      setExecuting(true);
      setLastResult(null);
    },
    onSettled: () => setExecuting(false),
    onSuccess: (result) => {
      setLastResult(result);
      queryClient.invalidateQueries({ queryKey: ['spine', 'pipelines'] });
    },
    onError: (error: Error) => {
      alert(`Failed to run pipeline: ${error.message}`);
    },
  });
  
  const handleRun = () => {
    if (confirm(`Run ${pipeline.name}?`)) {
      runMutation.mutate();
    }
  };

  return (
    <>
      <tr className={isSelected ? 'row-selected' : ''}>
        <td>
          <div className="pipeline-name-cell">
            <span className="pipeline-name">{pipeline.name}</span>
          </div>
        </td>
        <td>
          <span className="pipeline-desc">{pipeline.description || 'No description'}</span>
        </td>
        <td>
          <div className="action-buttons">
            <button 
              className="icon-btn" 
              title="View Details"
              onClick={onSelect}
            >
              <EyeIcon className="btn-icon" />
            </button>
            <button 
              className="icon-btn" 
              title="Run Now" 
              onClick={handleRun}
              disabled={executing}
            >
              {executing ? (
                <span className="spinner-sm" />
              ) : (
                <PlayIcon className="btn-icon" />
              )}
            </button>
          </div>
        </td>
      </tr>
      {lastResult && (
        <tr className="result-row">
          <td colSpan={3}>
            <div className={`execution-result ${lastResult.status}`}>
              <InformationCircleIcon className="result-icon" />
              <span className="result-status">{lastResult.status}</span>
              <span className="result-id">ID: {lastResult.execution_id}</span>
              {lastResult.rows_processed !== null && (
                <span className="result-rows">{lastResult.rows_processed} rows</span>
              )}
              {lastResult.duration_seconds != null && (
                <span className="result-duration">{lastResult.duration_seconds.toFixed(2)}s</span>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

interface PipelineDetailPanelProps {
  pipelineName: string;
  onClose: () => void;
}

function PipelineDetailPanel({ pipelineName, onClose }: PipelineDetailPanelProps) {
  const client = useSpineClient();
  const [params, setParams] = useState<Record<string, string>>({});
  const [dryRun, setDryRun] = useState(false);
  const [result, setResult] = useState<ExecutionResponse | null>(null);
  
  const { data: detail, isLoading, error } = useQuery({
    queryKey: ['spine', 'pipeline', pipelineName],
    queryFn: () => client.describePipeline(pipelineName),
  });

  const runMutation = useMutation({
    mutationFn: () => client.runPipeline(pipelineName, { params, dry_run: dryRun }),
    onSuccess: setResult,
  });

  const handleParamChange = (name: string, value: string) => {
    setParams(prev => ({ ...prev, [name]: value }));
  };

  if (isLoading) {
    return (
      <div className="detail-panel">
        <div className="spinner" />
      </div>
    );
  }

  if (error || !detail) {
    return (
      <div className="detail-panel">
        <p>Failed to load pipeline details</p>
        <button onClick={onClose}>Close</button>
      </div>
    );
  }

  return (
    <div className="detail-panel">
      <header className="detail-header">
        <h2>{detail.name}</h2>
        <button className="close-btn" onClick={onClose}>×</button>
      </header>
      
      <div className="detail-body">
        <p className="detail-desc">{detail.description}</p>
        
        {detail.is_ingest && (
          <div className="badge badge-info">Ingest Pipeline</div>
        )}

        {detail.required_params.length > 0 && (
          <section className="params-section">
            <h3>Required Parameters</h3>
            {detail.required_params.map(param => (
              <div key={param.name} className="param-field">
                <label>{param.name}</label>
                <span className="param-type">{param.type}</span>
                {param.choices ? (
                  <select 
                    value={params[param.name] ?? param.default ?? ''}
                    onChange={(e) => handleParamChange(param.name, e.target.value)}
                  >
                    <option value="">Select...</option>
                    {param.choices.map(c => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </select>
                ) : (
                  <input
                    type="text"
                    placeholder={param.default !== undefined ? String(param.default) : undefined}
                    value={params[param.name] ?? ''}
                    onChange={(e) => handleParamChange(param.name, e.target.value)}
                  />
                )}
                <span className="param-desc">{param.description}</span>
              </div>
            ))}
          </section>
        )}

        {detail.optional_params.length > 0 && (
          <section className="params-section">
            <h3>Optional Parameters</h3>
            {detail.optional_params.map(param => (
              <div key={param.name} className="param-field">
                <label>{param.name}</label>
                <span className="param-type">{param.type}</span>
                {param.choices ? (
                  <select 
                    value={params[param.name] ?? param.default ?? ''}
                    onChange={(e) => handleParamChange(param.name, e.target.value)}
                  >
                    <option value="">Default</option>
                    {param.choices.map(c => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </select>
                ) : (
                  <input
                    type="text"
                    placeholder={param.default !== undefined ? String(param.default) : 'Optional'}
                    value={params[param.name] ?? ''}
                    onChange={(e) => handleParamChange(param.name, e.target.value)}
                  />
                )}
                <span className="param-desc">{param.description}</span>
              </div>
            ))}
          </section>
        )}

        <div className="run-controls">
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={dryRun}
              onChange={(e) => setDryRun(e.target.checked)}
            />
            Dry run (validate only)
          </label>
          <button 
            className="btn btn-primary"
            onClick={() => runMutation.mutate()}
            disabled={runMutation.isPending}
          >
            {runMutation.isPending ? 'Running...' : 'Run Pipeline'}
          </button>
        </div>

        {result && (
          <div className={`execution-result ${result.status}`}>
            <h4>Execution Result</h4>
            <dl>
              <dt>Status</dt>
              <dd>{result.status}</dd>
              <dt>Execution ID</dt>
              <dd><code>{result.execution_id}</code></dd>
              {result.rows_processed !== null && (
                <>
                  <dt>Rows Processed</dt>
                  <dd>{result.rows_processed}</dd>
                </>
              )}
              {result.duration_seconds != null && (
                <>
                  <dt>Duration</dt>
                  <dd>{result.duration_seconds.toFixed(3)} seconds</dd>
                </>
              )}
            </dl>
          </div>
        )}

        {runMutation.error && (
          <div className="error-result">
            Failed: {runMutation.error instanceof Error ? runMutation.error.message : 'Unknown error'}
          </div>
        )}
      </div>
    </div>
  );
}
