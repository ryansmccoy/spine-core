/**
 * API client for the Orchestrator Lab.
 */

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export interface Execution {
  execution_id: string;
  orchestrator: string;
  pipeline: string;
  status: ExecutionStatus;
  params: Record<string, unknown>;
  external_run_id: string | null;
  external_url: string | null;
  created_at: string;
  started_at: string | null;
  ended_at: string | null;
  duration_ms: number | null;
  error_message: string | null;
  tasks: Task[];
}

export interface ExecutionSummary {
  execution_id: string;
  orchestrator: string;
  pipeline: string;
  status: ExecutionStatus;
  external_run_id: string | null;
  external_url: string | null;
  created_at: string;
  started_at: string | null;
  ended_at: string | null;
  duration_ms: number | null;
  task_count: number;
  completed_task_count: number;
  failed_task_count: number;
}

export interface Task {
  task_id: string;
  task_name: string;
  status: TaskStatus;
  started_at: string | null;
  ended_at: string | null;
  duration_ms: number | null;
  error_message: string | null;
  skip_reason: string | null;
  artifacts: Artifact[];
}

export interface Artifact {
  artifact_type: string;
  artifact_key: string;
  artifact_value: string;
  created_at: string;
}

export type ExecutionStatus = 
  | 'pending' 
  | 'queued' 
  | 'running' 
  | 'success' 
  | 'failed' 
  | 'cancelled' 
  | 'timeout';

export type TaskStatus = 
  | 'pending' 
  | 'running' 
  | 'success' 
  | 'failed' 
  | 'skipped' 
  | 'cancelled';

export interface CreateRunRequest {
  orchestrator: string;
  pipeline: string;
  params: Record<string, unknown>;
}

export interface CreateRunResponse {
  execution_id: string;
  orchestrator: string;
  pipeline: string;
  status: ExecutionStatus;
  created_at: string;
  external_run_id: string | null;
  external_url: string | null;
}

export interface ExecutionListResponse {
  executions: ExecutionSummary[];
  total: number;
  limit: number;
  offset: number;
}

/**
 * List recent executions.
 */
export async function listRuns(params?: {
  orchestrator?: string;
  pipeline?: string;
  status?: ExecutionStatus;
  limit?: number;
  offset?: number;
}): Promise<ExecutionListResponse> {
  const searchParams = new URLSearchParams();
  if (params?.orchestrator) searchParams.set('orchestrator', params.orchestrator);
  if (params?.pipeline) searchParams.set('pipeline', params.pipeline);
  if (params?.status) searchParams.set('status', params.status);
  if (params?.limit) searchParams.set('limit', params.limit.toString());
  if (params?.offset) searchParams.set('offset', params.offset.toString());

  const url = `${API_BASE}/api/v1/executions?${searchParams}`;
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to list runs: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Get execution details by ID.
 */
export async function getRun(executionId: string): Promise<Execution> {
  const response = await fetch(`${API_BASE}/api/v1/executions/${executionId}`);
  if (!response.ok) {
    throw new Error(`Failed to get run: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Create a new execution.
 */
export async function createRun(request: CreateRunRequest): Promise<CreateRunResponse> {
  const response = await fetch(`${API_BASE}/api/v1/executions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    throw new Error(`Failed to create run: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Cancel a running execution.
 */
export async function cancelRun(executionId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/api/v1/executions/${executionId}/cancel`, {
    method: 'POST',
  });
  if (!response.ok) {
    throw new Error(`Failed to cancel run: ${response.statusText}`);
  }
}

/**
 * Retry a failed execution.
 */
export async function retryRun(
  executionId: string, 
  fromFailure = true
): Promise<CreateRunResponse> {
  const response = await fetch(`${API_BASE}/api/v1/executions/${executionId}/retry`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ from_failure: fromFailure }),
  });
  if (!response.ok) {
    throw new Error(`Failed to retry run: ${response.statusText}`);
  }
  return response.json();
}
