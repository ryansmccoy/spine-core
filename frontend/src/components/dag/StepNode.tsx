/**
 * Custom React Flow node for workflow steps.
 * Renders step name, pipeline label, status indicator, and duration.
 */

import { Handle, Position, type NodeProps } from '@xyflow/react';
import { getStatusStyle } from '../../lib/colors';
import { formatDuration } from '../../lib/formatters';
import type { StepNodeData } from './dagre-layout';

export default function StepNode({ data }: NodeProps) {
  const { step, state } = data as StepNodeData;
  const style = getStatusStyle(state?.status);

  return (
    <div
      className={`bg-white border-2 ${style.border} rounded-lg px-4 py-3 min-w-[160px] shadow-sm hover:shadow-md transition-shadow cursor-pointer ${state?.status === 'RUNNING' || state?.status === 'running' ? 'animate-pulse' : ''}`}
    >
      <Handle type="target" position={Position.Left} className="!w-2 !h-2 !bg-gray-400 !border-none" />

      <div className="flex items-center gap-2">
        <div className={`w-2.5 h-2.5 rounded-full ${style.dot} shrink-0`} />
        <span className="font-semibold text-sm text-gray-800 truncate">{step.name}</span>
      </div>

      {step.pipeline && (
        <div className="text-[10px] text-gray-400 mt-0.5 truncate">{step.pipeline}</div>
      )}

      {state?.durationMs != null && (
        <div className="text-xs text-gray-500 mt-1 font-mono">
          {formatDuration(state.durationMs)}
        </div>
      )}

      {state?.error && (
        <div className="text-[10px] text-red-500 mt-1 truncate" title={state.error}>
          {state.error.slice(0, 40)}
        </div>
      )}

      <Handle type="source" position={Position.Right} className="!w-2 !h-2 !bg-gray-400 !border-none" />
    </div>
  );
}
