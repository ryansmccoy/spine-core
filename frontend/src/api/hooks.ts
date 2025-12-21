/** TanStack Query hooks for all spine-core API endpoints. */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from './client';
import type {
  Anomaly,
  Capabilities,
  CreateScheduleRequest,
  DatabaseHealth,
  DeadLetter,
  HealthStatus,
  PagedResponse,
  QualityResult,
  RunAccepted,
  RunDetail,
  RunEvent,
  RunSummary,
  RunWorkflowRequest,
  ScheduleDetail,
  ScheduleSummary,
  SubmitRunRequest,
  SuccessResponse,
  TableCount,
  UpdateScheduleRequest,
  WorkflowDetail,
  WorkflowSummary,
} from '../types/api';

// ── Health / Capabilities ───────────────────────────────────────────

export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: () => api.get<SuccessResponse<HealthStatus>>('/health'),
    refetchInterval: 15_000,
  });
}

export function useCapabilities() {
  return useQuery({
    queryKey: ['capabilities'],
    queryFn: () => api.get<SuccessResponse<Capabilities>>('/capabilities'),
  });
}

// ── Database ────────────────────────────────────────────────────────

export function useDatabaseHealth() {
  return useQuery({
    queryKey: ['database', 'health'],
    queryFn: () => api.get<SuccessResponse<DatabaseHealth>>('/database/health'),
    refetchInterval: 30_000,
  });
}

export function useTableCounts() {
  return useQuery({
    queryKey: ['database', 'tables'],
    queryFn: () => api.get<SuccessResponse<TableCount[]>>('/database/tables'),
  });
}

// ── Runs ────────────────────────────────────────────────────────────

export function useRuns(params?: {
  status?: string;
  pipeline?: string;
  limit?: number;
  offset?: number;
}) {
  const qs = new URLSearchParams();
  if (params?.status) qs.set('status', params.status);
  if (params?.pipeline) qs.set('pipeline', params.pipeline);
  if (params?.limit) qs.set('limit', String(params.limit));
  if (params?.offset) qs.set('offset', String(params.offset));
  const q = qs.toString();

  return useQuery({
    queryKey: ['runs', params],
    queryFn: () => api.get<PagedResponse<RunSummary>>(`/runs${q ? `?${q}` : ''}`),
    refetchInterval: 5_000,
  });
}

export function useRun(runId: string) {
  return useQuery({
    queryKey: ['runs', runId],
    queryFn: () => api.get<SuccessResponse<RunDetail>>(`/runs/${runId}`),
    enabled: !!runId,
    refetchInterval: 3_000,
  });
}

export function useRunEvents(runId: string) {
  return useQuery({
    queryKey: ['runs', runId, 'events'],
    queryFn: () => api.get<PagedResponse<RunEvent>>(`/runs/${runId}/events`),
    enabled: !!runId,
  });
}

export function useSubmitRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: SubmitRunRequest) =>
      api.post<SuccessResponse<RunAccepted>>('/runs', body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['runs'] }),
  });
}

export function useCancelRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) =>
      api.post<SuccessResponse<RunAccepted>>(`/runs/${runId}/cancel`, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['runs'] }),
  });
}

export function useRetryRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) =>
      api.post<SuccessResponse<RunAccepted>>(`/runs/${runId}/retry`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['runs'] }),
  });
}

// ── Workflows ───────────────────────────────────────────────────────

export function useWorkflows() {
  return useQuery({
    queryKey: ['workflows'],
    queryFn: () => api.get<PagedResponse<WorkflowSummary>>('/workflows'),
  });
}

export function useWorkflow(name: string) {
  return useQuery({
    queryKey: ['workflows', name],
    queryFn: () => api.get<SuccessResponse<WorkflowDetail>>(`/workflows/${name}`),
    enabled: !!name,
  });
}

export function useWorkflowRuns(name: string) {
  return useQuery({
    queryKey: ['workflows', name, 'runs'],
    queryFn: () => api.get<PagedResponse<RunSummary>>(`/runs?workflow=${encodeURIComponent(name)}&limit=5`),
    enabled: !!name,
  });
}

export function useRunWorkflow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      name,
      body,
    }: {
      name: string;
      body?: RunWorkflowRequest;
    }) => api.post<SuccessResponse<RunAccepted>>(`/workflows/${name}/run`, body ?? {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['workflows'] });
      qc.invalidateQueries({ queryKey: ['runs'] });
    },
  });
}

// ── Schedules ───────────────────────────────────────────────────────

export function useSchedules() {
  return useQuery({
    queryKey: ['schedules'],
    queryFn: () => api.get<PagedResponse<ScheduleSummary>>('/schedules'),
  });
}

export function useCreateSchedule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateScheduleRequest) =>
      api.post<SuccessResponse<ScheduleDetail>>('/schedules', body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['schedules'] }),
  });
}

export function useUpdateSchedule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: UpdateScheduleRequest }) =>
      api.put<SuccessResponse<ScheduleDetail>>(`/schedules/${id}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['schedules'] }),
  });
}

export function useDeleteSchedule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.del(`/schedules/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['schedules'] }),
  });
}

// ── DLQ ─────────────────────────────────────────────────────────────

export function useDLQ(params?: { pipeline?: string; limit?: number }) {
  const qs = new URLSearchParams();
  if (params?.pipeline) qs.set('pipeline', params.pipeline);
  if (params?.limit) qs.set('limit', String(params.limit));
  const q = qs.toString();

  return useQuery({
    queryKey: ['dlq', params],
    queryFn: () => api.get<PagedResponse<DeadLetter>>(`/dlq${q ? `?${q}` : ''}`),
  });
}

export function useReplayDLQ() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post(`/dlq/${id}/replay`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['dlq'] }),
  });
}

// ── Quality ─────────────────────────────────────────────────────────

export function useQuality(params?: { pipeline?: string; limit?: number }) {
  const qs = new URLSearchParams();
  if (params?.pipeline) qs.set('pipeline', params.pipeline);
  if (params?.limit) qs.set('limit', String(params.limit));
  const q = qs.toString();

  return useQuery({
    queryKey: ['quality', params],
    queryFn: () => api.get<PagedResponse<QualityResult>>(`/quality${q ? `?${q}` : ''}`),
  });
}

// ── Anomalies ───────────────────────────────────────────────────────

export function useAnomalies(params?: {
  pipeline?: string;
  severity?: string;
  limit?: number;
}) {
  const qs = new URLSearchParams();
  if (params?.pipeline) qs.set('pipeline', params.pipeline);
  if (params?.severity) qs.set('severity', params.severity);
  if (params?.limit) qs.set('limit', String(params.limit));
  const q = qs.toString();

  return useQuery({
    queryKey: ['anomalies', params],
    queryFn: () => api.get<PagedResponse<Anomaly>>(`/anomalies${q ? `?${q}` : ''}`),
  });
}

// ── Stats (TanStack Query) ──────────────────────────────────────────

export interface RunStats {
  total: number;
  pending: number;
  running: number;
  completed: number;
  failed: number;
  cancelled: number;
  dead_lettered: number;
}

export interface QueueDepth {
  lane: string;
  pending: number;
  running: number;
}

export interface WorkerInfo {
  worker_id: string;
  pid: number;
  started_at: string;
  poll_interval: number;
  max_workers: number;
  status: string;
  runs_processed: number;
  runs_failed: number;
  hostname: string;
}

export function useRunStats() {
  return useQuery({
    queryKey: ['stats', 'runs'],
    queryFn: () => api.get<SuccessResponse<RunStats>>('/stats/runs'),
    refetchInterval: 5_000,
  });
}

export function useQueueDepths() {
  return useQuery({
    queryKey: ['stats', 'queues'],
    queryFn: () => api.get<SuccessResponse<QueueDepth[]>>('/stats/queues'),
    refetchInterval: 5_000,
  });
}

export function useWorkers() {
  return useQuery({
    queryKey: ['stats', 'workers'],
    queryFn: () => api.get<SuccessResponse<WorkerInfo[]>>('/stats/workers'),
    refetchInterval: 5_000,
  });
}
