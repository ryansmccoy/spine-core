/**
 * Dagre layout utility — converts workflow steps into React Flow nodes + edges.
 */

import type { Node, Edge } from '@xyflow/react';
import type { WorkflowStep } from '../../types/api';
import { getStatusHex } from '../../lib/colors';

export interface StepState {
  status: string;
  startedAt?: string | null;
  finishedAt?: string | null;
  durationMs?: number | null;
  error?: string | null;
}

export interface StepNodeData {
  step: WorkflowStep;
  state?: StepState;
  [key: string]: unknown;
}

/**
 * Convert workflow steps + optional step states into React Flow graph elements.
 * Uses dagre for automatic hierarchical layout.
 */
export function stepsToFlow(
  steps: WorkflowStep[],
  stepStates?: Record<string, StepState>,
  direction: 'LR' | 'TB' = 'LR',
): { nodes: Node<StepNodeData>[]; edges: Edge[] } {
  if (!steps.length) return { nodes: [], edges: [] };

  const NODE_WIDTH = 180;
  const NODE_HEIGHT = 72;

  // Build nodes
  const nodes: Node<StepNodeData>[] = steps.map((step) => ({
    id: step.name,
    type: 'stepNode',
    data: { step, state: stepStates?.[step.name] },
    position: { x: 0, y: 0 },
  }));

  // Build edges from depends_on
  const edges: Edge[] = steps.flatMap((step) =>
    (step.depends_on ?? [])
      .filter((dep) => steps.some((s) => s.name === dep))
      .map((dep) => {
        const targetState = stepStates?.[step.name];
        const isRunning = targetState?.status === 'RUNNING' || targetState?.status === 'running';
        return {
          id: `${dep}->${step.name}`,
          source: dep,
          target: step.name,
          animated: isRunning,
          style: {
            stroke: targetState ? getStatusHex(targetState.status) : '#94a3b8',
            strokeWidth: 2,
          },
        };
      }),
  );

  // Simple layered layout (no dagre import needed at runtime for small graphs)
  // For robustness we do our own topological sort + layer assignment
  const layers = assignLayers(steps);
  const maxPerLayer = Math.max(...Object.values(layers).map((arr) => arr.length), 1);

  const isHorizontal = direction === 'LR';
  const nodeSpacingX = isHorizontal ? NODE_WIDTH + 80 : NODE_WIDTH + 40;
  const nodeSpacingY = isHorizontal ? NODE_HEIGHT + 30 : NODE_HEIGHT + 60;

  // Position nodes by layer
  for (const [layerStr, layerNodes] of Object.entries(layers)) {
    const layer = parseInt(layerStr, 10);
    const count = layerNodes.length;
    layerNodes.forEach((stepName, idx) => {
      const node = nodes.find((n) => n.id === stepName);
      if (!node) return;
      const offset = (idx - (count - 1) / 2) * (isHorizontal ? nodeSpacingY : nodeSpacingX);
      if (isHorizontal) {
        node.position = {
          x: layer * nodeSpacingX,
          y: offset + maxPerLayer * nodeSpacingY / 2,
        };
      } else {
        node.position = {
          x: offset + maxPerLayer * nodeSpacingX / 2,
          y: layer * nodeSpacingY,
        };
      }
    });
  }

  return { nodes, edges };
}

/**
 * Topological sort + layer assignment for DAG layout.
 */
function assignLayers(steps: WorkflowStep[]): Record<number, string[]> {
  const nameSet = new Set(steps.map((s) => s.name));
  const depths: Record<string, number> = {};

  function getDepth(name: string, visited: Set<string>): number {
    if (depths[name] !== undefined) return depths[name];
    if (visited.has(name)) return 0; // cycle guard
    visited.add(name);

    const step = steps.find((s) => s.name === name);
    if (!step || !step.depends_on || step.depends_on.length === 0) {
      depths[name] = 0;
      return 0;
    }

    const maxParent = Math.max(
      ...step.depends_on
        .filter((d) => nameSet.has(d))
        .map((d) => getDepth(d, visited)),
      -1,
    );
    depths[name] = maxParent + 1;
    return depths[name];
  }

  steps.forEach((s) => getDepth(s.name, new Set()));

  const layers: Record<number, string[]> = {};
  for (const [name, depth] of Object.entries(depths)) {
    if (!layers[depth]) layers[depth] = [];
    layers[depth].push(name);
  }
  return layers;
}
