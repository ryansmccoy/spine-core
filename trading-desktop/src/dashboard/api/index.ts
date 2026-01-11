/**
 * Dashboard API Client
 * 
 * Connects to the backend control plane endpoints
 */

const API_BASE = import.meta.env.VITE_API_URL || '';

// ─────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────

export interface SystemHealth {
  status: 'healthy' | 'degraded' | 'unhealthy';
  services: ServiceHealth[];
  timestamp: string;
}

export interface ServiceHealth {
  name: string;
  status: 'healthy' | 'degraded' | 'unhealthy';
  latency_ms: number;
  message?: string;
}

export interface ExecutionSummary {
  running: number;
  pending: number;
  success: number;
  failed: number;
  success_rate: number;
  running_change?: number;
}

export interface QueueStats {
  total_depth: number;
  total_consumers: number;
  depth_change?: number;
  queues: QueueInfo[];
}

export interface QueueInfo {
  name: string;
  depth: number;
  consumers: number;
  rate: number;
  status: 'healthy' | 'warning' | 'backlogged';
}

export interface Execution {
  id: string;
  type: 'pipeline' | 'job' | 'scheduled';
  name: string;
  status: 'pending' | 'running' | 'success' | 'failed' | 'cancelled';
  parent_id?: string;
  root_id: string;
  trigger: 'scheduled' | 'manual' | 'dependency' | 'replay';
  triggered_by: string;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  duration_ms?: number;
  error?: string;
  progress?: number;
}

export interface Pipeline {
  id: string;
  name: string;
  description: string;
  schedule?: string;
  last_run?: string;
  last_status?: string;
  avg_duration_ms?: number;
  success_rate?: number;
}

export interface Incident {
  id: string;
  title: string;
  severity: 'critical' | 'warning' | 'info';
  status: 'open' | 'acknowledged' | 'resolved' | 'muted';
  category: string;
  root_cause?: string;
  impact_summary: string;
  related_executions: string[];
  created_at: string;
  acknowledged_at?: string;
  resolved_at?: string;
}

export interface Failure {
  id: string;
  name: string;
  error: string;
  timestamp: string;
  impact?: string;
  execution_id: string;
}

// ─────────────────────────────────────────────────────────────
// API Client
// ─────────────────────────────────────────────────────────────

async function fetchApi<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
    },
    ...options,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  return response.json();
}

export const dashboardApi = {
  // Health & Status
  getSystemHealth: (): Promise<SystemHealth> =>
    fetchApi('/api/v1/dashboard/health'),

  // Executions
  getExecutionsSummary: (): Promise<ExecutionSummary> =>
    fetchApi('/api/v1/dashboard/executions/summary'),

  getExecutions: (params?: { status?: string; type?: string; limit?: number }): Promise<Execution[]> => {
    const query = new URLSearchParams();
    if (params?.status) query.set('status', params.status);
    if (params?.type) query.set('type', params.type);
    if (params?.limit) query.set('limit', String(params.limit));
    return fetchApi(`/api/v1/dashboard/executions?${query}`);
  },

  getExecution: (id: string): Promise<Execution> =>
    fetchApi(`/api/v1/dashboard/executions/${id}`),

  // Pipelines
  getPipelines: (): Promise<Pipeline[]> =>
    fetchApi('/api/v1/dashboard/pipelines'),

  getPipeline: (id: string): Promise<Pipeline> =>
    fetchApi(`/api/v1/dashboard/pipelines/${id}`),

  triggerPipeline: (id: string, params?: Record<string, unknown>): Promise<Execution> =>
    fetchApi(`/api/v1/dashboard/pipelines/${id}/trigger`, {
      method: 'POST',
      body: JSON.stringify(params || {}),
    }),

  // Queues
  getQueuesStats: (): Promise<QueueStats> =>
    fetchApi('/api/v1/dashboard/queues'),

  // Incidents
  getIncidents: (status?: string): Promise<Incident[]> => {
    const query = status ? `?status=${status}` : '';
    return fetchApi(`/api/v1/dashboard/incidents${query}`);
  },

  acknowledgeIncident: (id: string, reason?: string): Promise<Incident> =>
    fetchApi(`/api/v1/dashboard/incidents/${id}/acknowledge`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),

  resolveIncident: (id: string, resolution?: string): Promise<Incident> =>
    fetchApi(`/api/v1/dashboard/incidents/${id}/resolve`, {
      method: 'POST',
      body: JSON.stringify({ resolution }),
    }),

  // Failures
  getRecentFailures: (limit: number = 10): Promise<Failure[]> =>
    fetchApi(`/api/v1/dashboard/failures?limit=${limit}`),

  // Actions
  retryExecution: (id: string, reason?: string): Promise<Execution> =>
    fetchApi(`/api/v1/dashboard/executions/${id}/retry`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),

  cancelExecution: (id: string, reason?: string): Promise<Execution> =>
    fetchApi(`/api/v1/dashboard/executions/${id}/cancel`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),
};

export default dashboardApi;
