/**
 * Slide-out drawer showing details for a selected workflow step.
 * Opens when a user clicks a node in the WorkflowDAG.
 */

import type { WorkflowStep } from '../../types/api';
import type { StepState } from '../dag/dagre-layout';
import { getStatusStyle } from '../../lib/colors';
import { formatDuration, formatTime } from '../../lib/formatters';

interface StepDetailDrawerProps {
  step: WorkflowStep;
  state?: StepState;
  onClose: () => void;
  onViewLogs?: (stepName: string) => void;
}

export default function StepDetailDrawer({ step, state, onClose, onViewLogs }: StepDetailDrawerProps) {
  const style = state ? getStatusStyle(state.status) : null;

  return (
    <div className="fixed inset-y-0 right-0 w-80 bg-white shadow-xl border-l border-gray-200 z-40 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
        <h3 className="text-sm font-bold text-gray-900 truncate">Step: {step.name}</h3>
        <button
          onClick={onClose}
          className="text-gray-400 hover:text-gray-600 text-lg leading-none"
        >
          &times;
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {/* Pipeline */}
        {step.pipeline && (
          <div>
            <label className="text-[10px] font-medium text-gray-500 uppercase tracking-wide">Pipeline</label>
            <p className="text-sm font-mono text-gray-700">{step.pipeline}</p>
          </div>
        )}

        {/* Description */}
        {step.description && (
          <div>
            <label className="text-[10px] font-medium text-gray-500 uppercase tracking-wide">Description</label>
            <p className="text-sm text-gray-600">{step.description}</p>
          </div>
        )}

        {/* Dependencies */}
        {step.depends_on && step.depends_on.length > 0 && (
          <div>
            <label className="text-[10px] font-medium text-gray-500 uppercase tracking-wide">Dependencies</label>
            <div className="flex flex-wrap gap-1 mt-1">
              {step.depends_on.map((dep) => (
                <span key={dep} className="inline-flex items-center px-2 py-0.5 rounded text-xs bg-gray-100 text-gray-600 font-mono">
                  {dep}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Parameters */}
        {step.params && Object.keys(step.params).length > 0 && (
          <div>
            <label className="text-[10px] font-medium text-gray-500 uppercase tracking-wide">Parameters</label>
            <pre className="text-xs bg-gray-50 rounded p-2 mt-1 overflow-x-auto whitespace-pre-wrap break-words max-h-40 overflow-y-auto">
              {JSON.stringify(step.params, null, 2)}
            </pre>
          </div>
        )}

        {/* Run State (if available) */}
        {state && (
          <div className="border-t border-gray-100 pt-4">
            <label className="text-[10px] font-medium text-gray-500 uppercase tracking-wide mb-2 block">
              Run State
            </label>
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <div className={`w-2.5 h-2.5 rounded-full ${style?.dot}`} />
                <span className={`text-sm font-medium ${style?.text}`}>
                  {state.status}
                </span>
              </div>

              {state.durationMs != null && (
                <div className="flex justify-between text-xs">
                  <span className="text-gray-500">Duration</span>
                  <span className="font-mono">{formatDuration(state.durationMs)}</span>
                </div>
              )}

              {state.startedAt && (
                <div className="flex justify-between text-xs">
                  <span className="text-gray-500">Started</span>
                  <span>{formatTime(state.startedAt)}</span>
                </div>
              )}

              {state.finishedAt && (
                <div className="flex justify-between text-xs">
                  <span className="text-gray-500">Finished</span>
                  <span>{formatTime(state.finishedAt)}</span>
                </div>
              )}

              {state.error && (
                <div>
                  <label className="text-[10px] font-medium text-red-500 uppercase tracking-wide">Error</label>
                  <pre className="text-xs text-red-600 bg-red-50 rounded p-2 mt-1 whitespace-pre-wrap break-words max-h-32 overflow-y-auto">
                    {state.error}
                  </pre>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Footer actions */}
      {onViewLogs && state && (
        <div className="px-4 py-3 border-t border-gray-100">
          <button
            onClick={() => onViewLogs(step.name)}
            className="w-full text-center text-sm text-spine-600 hover:text-spine-700 font-medium py-2 bg-spine-50 rounded-lg hover:bg-spine-100 transition-colors"
          >
            View Logs for This Step
          </button>
        </div>
      )}
    </div>
  );
}
