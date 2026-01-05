/**
 * Spine Context - React Context for Market Spine API
 * 
 * Provides:
 * - SpineClient instance
 * - Capabilities for feature gating
 * - Connection status
 * - Health information
 */

import { createContext, useContext, useState, useCallback, useMemo, type ReactNode } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { SpineClient, createSpineClient } from './spineClient';
import type { SpineCapabilities, HealthResponse, SpineTier } from './spineTypes';
import { SpineError } from './spineTypes';

// ─────────────────────────────────────────────────────────────
// Context Types
// ─────────────────────────────────────────────────────────────

export type ConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'error';

export interface SpineContextValue {
  /** The SpineClient instance */
  client: SpineClient;
  
  /** Current connection status */
  status: ConnectionStatus;
  
  /** True when capabilities have loaded */
  isReady: boolean;
  
  /** Backend capabilities (null until loaded) */
  capabilities: SpineCapabilities | null;
  
  /** Latest health check result */
  health: HealthResponse | null;
  
  /** Current tier (convenience) */
  tier: SpineTier | null;
  
  /** Last error if any */
  error: SpineError | null;
  
  /** Reconnect to backend */
  reconnect: () => void;
}

const SpineContext = createContext<SpineContextValue | null>(null);

// ─────────────────────────────────────────────────────────────
// Provider Component
// ─────────────────────────────────────────────────────────────

export interface SpineProviderProps {
  children: ReactNode;
  /** Custom client instance (optional) */
  client?: SpineClient;
  /** Polling interval for health checks in ms (default: 30000) */
  healthPollInterval?: number;
}

export function SpineProvider({ 
  children, 
  client: customClient,
  healthPollInterval = 30000,
}: SpineProviderProps) {
  const [client] = useState(() => customClient ?? createSpineClient());
  const queryClient = useQueryClient();

  // Fetch capabilities on mount
  const { 
    data: capabilities, 
    isLoading: capabilitiesLoading,
    error: capabilitiesError,
    refetch: refetchCapabilities,
  } = useQuery({
    queryKey: ['spine', 'capabilities'],
    queryFn: () => client.getCapabilities(),
    retry: 2,
    retryDelay: 1000,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });

  // Derive connection status from query states (no setState in effects)
  const status: ConnectionStatus = useMemo(() => {
    if (capabilitiesLoading) return 'connecting';
    if (capabilitiesError) return 'error';
    if (capabilities) return 'connected';
    return 'connecting';
  }, [capabilitiesLoading, capabilitiesError, capabilities]);

  // Derive error from query error
  const error: SpineError | null = useMemo(() => {
    if (!capabilitiesError) return null;
    return capabilitiesError instanceof SpineError
      ? capabilitiesError
      : new SpineError({
          code: 'CONNECTION_ERROR',
          message: capabilitiesError instanceof Error ? capabilitiesError.message : 'Unknown error',
        });
  }, [capabilitiesError]);

  // Poll health when connected
  const { 
    data: health,
  } = useQuery({
    queryKey: ['spine', 'health'],
    queryFn: () => client.getHealth(),
    refetchInterval: healthPollInterval,
    enabled: status === 'connected',
  });

  const reconnect = useCallback(() => {
    client.clearCapabilitiesCache();
    queryClient.invalidateQueries({ queryKey: ['spine'] });
    refetchCapabilities();
  }, [client, queryClient, refetchCapabilities]);

  const value: SpineContextValue = {
    client,
    status,
    isReady: !!capabilities,
    capabilities: capabilities ?? null,
    health: health ?? null,
    tier: capabilities?.tier ?? null,
    error,
    reconnect,
  };

  return (
    <SpineContext.Provider value={value}>
      {children}
    </SpineContext.Provider>
  );
}

// ─────────────────────────────────────────────────────────────
// Hooks
// ─────────────────────────────────────────────────────────────

/**
 * Access the Spine context
 * @throws Error if used outside SpineProvider
 */
export function useSpine(): SpineContextValue {
  const context = useContext(SpineContext);
  if (!context) {
    throw new Error('useSpine must be used within a SpineProvider');
  }
  return context;
}

/**
 * Access the Spine client directly
 */
export function useSpineClient(): SpineClient {
  return useSpine().client;
}

/**
 * Access current capabilities
 */
export function useCapabilities(): SpineCapabilities | null {
  return useSpine().capabilities;
}

/**
 * Check if a specific feature is available
 */
export function useFeature(feature: keyof SpineCapabilities): boolean {
  const capabilities = useCapabilities();
  if (!capabilities) return false;
  return !!capabilities[feature];
}

/**
 * Check if running on a specific tier or higher
 */
export function useTierAtLeast(minimumTier: SpineTier): boolean {
  const tier = useSpine().tier;
  if (!tier) return false;
  
  const tierOrder: SpineTier[] = ['basic', 'intermediate', 'full'];
  const currentIndex = tierOrder.indexOf(tier);
  const minimumIndex = tierOrder.indexOf(minimumTier);
  
  return currentIndex >= minimumIndex;
}

// ─────────────────────────────────────────────────────────────
// Feature Gate Component
// ─────────────────────────────────────────────────────────────

export interface FeatureGateProps {
  /** Feature to check (from SpineCapabilities) */
  feature?: keyof SpineCapabilities;
  /** Minimum tier required */
  tier?: SpineTier;
  /** Content to show when feature is available */
  children: ReactNode;
  /** Fallback content when feature is not available */
  fallback?: ReactNode;
  /** Show loading state while capabilities load */
  showLoading?: boolean;
}

/**
 * Conditionally render content based on backend capabilities
 */
export function FeatureGate({ 
  feature, 
  tier, 
  children, 
  fallback = null,
  showLoading = false,
}: FeatureGateProps) {
  const { capabilities, isReady } = useSpine();
  
  if (!isReady) {
    return showLoading ? <div className="loading-spinner" /> : null;
  }

  // Check feature flag
  if (feature && !capabilities?.[feature]) {
    return <>{fallback}</>;
  }

  // Check tier requirement
  if (tier) {
    const tierOrder: SpineTier[] = ['basic', 'intermediate', 'full'];
    const currentTier = capabilities?.tier ?? 'basic';
    const currentIndex = tierOrder.indexOf(currentTier);
    const requiredIndex = tierOrder.indexOf(tier);
    
    if (currentIndex < requiredIndex) {
      return <>{fallback}</>;
    }
  }

  return <>{children}</>;
}

// ─────────────────────────────────────────────────────────────
// Tier Upgrade Message Component
// ─────────────────────────────────────────────────────────────

export interface TierUpgradeMessageProps {
  feature: string;
  requiredTier: SpineTier;
  className?: string;
}

/**
 * Standard message shown when a feature requires a higher tier
 */
export function TierUpgradeMessage({ feature, requiredTier, className = '' }: TierUpgradeMessageProps) {
  const tier = useSpine().tier;
  
  return (
    <div className={`tier-upgrade-message ${className}`}>
      <div className="upgrade-icon">🔒</div>
      <h3>{feature} requires {requiredTier} tier</h3>
      <p>
        You are currently using the <strong>{tier}</strong> tier.
        Upgrade to <strong>{requiredTier}</strong> to access this feature.
      </p>
    </div>
  );
}
