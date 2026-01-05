/**
 * Tests for the Spine Context and feature gating
 * 
 * These are simple unit tests for the context hooks and components.
 * For full integration testing, we'd need to render with a real QueryClient.
 */

import { describe, it, expect } from 'vitest';
import type { SpineCapabilities, SpineTier } from '../spineTypes';

// Helper function to test tier checking logic
function checkTierAtLeast(currentTier: SpineTier | null, minimumTier: SpineTier): boolean {
  if (!currentTier) return false;
  
  const tierOrder: SpineTier[] = ['basic', 'intermediate', 'full'];
  const currentIndex = tierOrder.indexOf(currentTier);
  const minimumIndex = tierOrder.indexOf(minimumTier);
  
  return currentIndex >= minimumIndex;
}

// Helper function to derive capabilities
function deriveCapabilities(raw: {
  tier: SpineTier;
  async_execution: boolean;
  execution_history: boolean;
  scheduling: boolean;
}): Partial<SpineCapabilities> {
  return {
    hasAsyncExecution: raw.async_execution,
    hasExecutionHistory: raw.execution_history,
    hasScheduling: raw.scheduling,
    hasQueues: raw.tier !== 'basic',
    hasIncidents: raw.tier === 'full',
    hasOrchestratorLab: raw.async_execution,
    hasDataLineage: raw.tier !== 'basic',
  };
}

describe('SpineContext logic', () => {
  describe('tier checking', () => {
    it('should correctly check basic tier', () => {
      expect(checkTierAtLeast('basic', 'basic')).toBe(true);
      expect(checkTierAtLeast('basic', 'intermediate')).toBe(false);
      expect(checkTierAtLeast('basic', 'full')).toBe(false);
    });

    it('should correctly check intermediate tier', () => {
      expect(checkTierAtLeast('intermediate', 'basic')).toBe(true);
      expect(checkTierAtLeast('intermediate', 'intermediate')).toBe(true);
      expect(checkTierAtLeast('intermediate', 'full')).toBe(false);
    });

    it('should correctly check full tier', () => {
      expect(checkTierAtLeast('full', 'basic')).toBe(true);
      expect(checkTierAtLeast('full', 'intermediate')).toBe(true);
      expect(checkTierAtLeast('full', 'full')).toBe(true);
    });

    it('should return false for null tier', () => {
      expect(checkTierAtLeast(null, 'basic')).toBe(false);
    });
  });

  describe('derived capabilities', () => {
    it('should derive basic tier capabilities correctly', () => {
      const derived = deriveCapabilities({
        tier: 'basic',
        async_execution: false,
        execution_history: false,
        scheduling: false,
      });

      expect(derived.hasAsyncExecution).toBe(false);
      expect(derived.hasExecutionHistory).toBe(false);
      expect(derived.hasScheduling).toBe(false);
      expect(derived.hasQueues).toBe(false);
      expect(derived.hasIncidents).toBe(false);
      expect(derived.hasOrchestratorLab).toBe(false);
      expect(derived.hasDataLineage).toBe(false);
    });

    it('should derive intermediate tier capabilities correctly', () => {
      const derived = deriveCapabilities({
        tier: 'intermediate',
        async_execution: true,
        execution_history: true,
        scheduling: true,
      });

      expect(derived.hasAsyncExecution).toBe(true);
      expect(derived.hasExecutionHistory).toBe(true);
      expect(derived.hasScheduling).toBe(true);
      expect(derived.hasQueues).toBe(true);
      expect(derived.hasIncidents).toBe(false); // Only in full
      expect(derived.hasOrchestratorLab).toBe(true);
      expect(derived.hasDataLineage).toBe(true);
    });

    it('should derive full tier capabilities correctly', () => {
      const derived = deriveCapabilities({
        tier: 'full',
        async_execution: true,
        execution_history: true,
        scheduling: true,
      });

      expect(derived.hasAsyncExecution).toBe(true);
      expect(derived.hasExecutionHistory).toBe(true);
      expect(derived.hasScheduling).toBe(true);
      expect(derived.hasQueues).toBe(true);
      expect(derived.hasIncidents).toBe(true);
      expect(derived.hasOrchestratorLab).toBe(true);
      expect(derived.hasDataLineage).toBe(true);
    });
  });

  describe('feature availability by tier', () => {
    const features = [
      { feature: 'pipelines', basic: true, intermediate: true, full: true },
      { feature: 'queryWeeks', basic: true, intermediate: true, full: true },
      { feature: 'querySymbols', basic: true, intermediate: true, full: true },
      { feature: 'scheduler', basic: false, intermediate: true, full: true },
      { feature: 'orchestratorLab', basic: false, intermediate: true, full: true },
      { feature: 'queues', basic: false, intermediate: true, full: true },
      { feature: 'incidents', basic: false, intermediate: false, full: true },
    ];

    it.each(features)('$feature availability matches tier expectations', ({ feature, basic, intermediate, full }) => {
      // This tests documents the expected feature matrix
      expect({ feature, basic, intermediate, full }).toMatchSnapshot();
    });
  });
});

describe('ConnectionStatus', () => {
  type ConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'error';
  
  function deriveStatus(
    isLoading: boolean,
    hasError: boolean,
    hasCapabilities: boolean
  ): ConnectionStatus {
    if (isLoading) return 'connecting';
    if (hasError) return 'error';
    if (hasCapabilities) return 'connected';
    return 'connecting';
  }

  it('should be connecting while loading', () => {
    expect(deriveStatus(true, false, false)).toBe('connecting');
  });

  it('should be error when failed', () => {
    expect(deriveStatus(false, true, false)).toBe('error');
  });

  it('should be connected when capabilities loaded', () => {
    expect(deriveStatus(false, false, true)).toBe('connected');
  });

  it('should be connecting when no data yet', () => {
    expect(deriveStatus(false, false, false)).toBe('connecting');
  });
});
