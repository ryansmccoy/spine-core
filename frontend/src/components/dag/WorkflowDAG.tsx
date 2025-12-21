/**
 * Interactive DAG graph for workflow visualization using React Flow.
 * Replaces the old linear StepGraph with a real directed acyclic graph.
 * Supports step state overlay from run execution data.
 */

import { useCallback, useMemo } from 'react';
import {
  ReactFlow,
  Controls,
  MiniMap,
  Background,
  BackgroundVariant,
  useNodesState,
  useEdgesState,
  type Node,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import StepNode from './StepNode';
import { stepsToFlow, type StepState } from './dagre-layout';
import { getStatusHex } from '../../lib/colors';
import type { WorkflowStep } from '../../types/api';

const nodeTypes = { stepNode: StepNode };

interface WorkflowDAGProps {
  steps: WorkflowStep[];
  stepStates?: Record<string, StepState>;
  onStepClick?: (stepName: string) => void;
  className?: string;
  /** Height in pixels or CSS value (default: 350) */
  height?: number | string;
  /** Show MiniMap overlay (default: false for small graphs, true for >=8 steps) */
  showMinimap?: boolean;
}

export default function WorkflowDAG({
  steps,
  stepStates,
  onStepClick,
  className = '',
  height = 350,
  showMinimap,
}: WorkflowDAGProps) {
  const { initialNodes, initialEdges } = useMemo(() => {
    const { nodes, edges } = stepsToFlow(steps, stepStates, 'LR');
    return { initialNodes: nodes, initialEdges: edges };
  }, [steps, stepStates]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  // Update nodes + edges when steps or states change
  useMemo(() => {
    setNodes(initialNodes);
    setEdges(initialEdges);
  }, [initialNodes, initialEdges, setNodes, setEdges]);

  const handleNodeClick = useCallback(
    (_event: React.MouseEvent, node: Node) => {
      onStepClick?.(node.id);
    },
    [onStepClick],
  );

  const shouldShowMinimap = showMinimap ?? steps.length >= 8;
  const heightStyle = typeof height === 'number' ? `${height}px` : height;

  if (!steps.length) {
    return (
      <div className="flex items-center justify-center h-32 text-sm text-gray-400">
        No steps defined
      </div>
    );
  }

  return (
    <div className={`rounded-lg border border-gray-200 bg-gray-50 overflow-hidden ${className}`} style={{ height: heightStyle }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        minZoom={0.3}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
        defaultEdgeOptions={{
          type: 'smoothstep',
          style: { strokeWidth: 2 },
        }}
      >
        <Controls
          showInteractive={false}
          className="!bg-white !border !border-gray-200 !shadow-sm"
        />
        <Background variant={BackgroundVariant.Dots} gap={16} size={1} color="#e5e7eb" />
        {shouldShowMinimap && (
          <MiniMap
            nodeColor={(node) => {
              const state = (node.data as { state?: StepState })?.state;
              return state ? getStatusHex(state.status) : '#d1d5db';
            }}
            maskColor="rgba(0,0,0,0.08)"
            className="!bg-white !border !border-gray-200"
          />
        )}
      </ReactFlow>
    </div>
  );
}
