/** TanStack Query hooks for all spine-core API endpoints. */

import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query';
import { api } from './client';
import type {
  Anomaly,
  BackupResponse,
  Capabilities,
  ContextSnapshot,
  CreateSessionRequest,
  CreateScheduleRequest,
  DatabaseConfig,
  DatabaseHealth,
  DeadLetter,
  ExampleItem,
  ExampleSource,
  ExamplesSummary,
  FunctionCreateRequest,
  FunctionDetail,
  FunctionSummary,
  FunctionTemplate,
  FunctionUpdateRequest,
  HealthStatus,
  InvocationLog,
  InvokeRequest,
  InvokeResult,
  PagedResponse,
  PlaygroundExample,
  PlaygroundSession,
  PlaygroundWorkflow,
  QualityResult,
  QueryResponse,
  RunAccepted,
  RunDetail,
  RunEvent,
  RunExamplesResponse,
  RunHistoryBucket,
  RunLogEntry,
  RunStep,
  RunSummary,
  RunWorkflowRequest,
  ScheduleDetail,
  ScheduleSummary,
  StepPreview,
  StepSnapshot,
  SubmitRunRequest,
  SuccessResponse,
  TableCount,
  TableSchema,
  UpdateScheduleRequest,
  VacuumResponse,
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

export function useDatabaseConfig() {
  return useQuery({
    queryKey: ['database', 'config'],
    queryFn: () => api.get<SuccessResponse<DatabaseConfig>>('/database/config'),
  });
}

export function useDatabaseSchema() {
  return useQuery({
    queryKey: ['database', 'schema'],
    queryFn: () => api.get<SuccessResponse<TableSchema[]>>('/database/schema'),
  });
}

export function useRunQuery() {
  return useMutation({
    mutationFn: (body: { sql: string; limit?: number }) =>
      api.post<SuccessResponse<QueryResponse>>('/database/query', body),
  });
}

export function useVacuum() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<SuccessResponse<VacuumResponse>>('/database/vacuum'),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['database'] });
    },
  });
}

export function useBackup() {
  return useMutation({
    mutationFn: () => api.post<SuccessResponse<BackupResponse>>('/database/backup'),
  });
}

export function useInitDatabase() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (dryRun: boolean = false) =>
      api.post<SuccessResponse<unknown>>(`/database/init?dry_run=${dryRun}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['database'] });
    },
  });
}

export function usePurgeData() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (params: { older_than_days: number; dry_run: boolean }) =>
      api.post<SuccessResponse<unknown>>(
        `/database/purge?older_than_days=${params.older_than_days}&dry_run=${params.dry_run}`
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['database'] });
    },
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
    placeholderData: keepPreviousData,
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

export function useRunSteps(runId: string, opts?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ['runs', runId, 'steps'],
    queryFn: () => api.get<PagedResponse<RunStep>>(`/runs/${runId}/steps?limit=200`),
    enabled: (opts?.enabled ?? true) && !!runId,
    refetchInterval: 5_000,
  });
}

export function useRunHistory(params?: { hours?: number; buckets?: number }) {
  const qs = new URLSearchParams();
  if (params?.hours) qs.set('hours', String(params.hours));
  if (params?.buckets) qs.set('buckets', String(params.buckets));
  const q = qs.toString();

  return useQuery({
    queryKey: ['stats', 'runs', 'history', params],
    queryFn: () => api.get<SuccessResponse<RunHistoryBucket[]>>(`/stats/runs/history${q ? `?${q}` : ''}`),
    refetchInterval: 30_000,
    placeholderData: keepPreviousData,
  });
}

export function useRunLogs(runId: string, params?: { step?: string; level?: string; limit?: number }) {
  const qs = new URLSearchParams();
  if (params?.step) qs.set('step', params.step);
  if (params?.level) qs.set('level', params.level);
  if (params?.limit) qs.set('limit', String(params.limit));
  const q = qs.toString();

  return useQuery({
    queryKey: ['runs', runId, 'logs', params],
    queryFn: () => api.get<PagedResponse<RunLogEntry>>(`/runs/${runId}/logs${q ? `?${q}` : ''}`),
    enabled: !!runId,
    refetchInterval: 5_000,
  });
}

// ── Workflows ───────────────────────────────────────────────────────

export function useWorkflows() {
  return useQuery({
    queryKey: ['workflows'],
    queryFn: () => api.get<PagedResponse<WorkflowSummary>>('/workflows'),
    placeholderData: keepPreviousData,
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
    placeholderData: keepPreviousData,
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
    placeholderData: keepPreviousData,
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

// ── Examples ────────────────────────────────────────────────────────

export function useExamples(params?: { category?: string; limit?: number }) {
  const qs = new URLSearchParams();
  if (params?.category) qs.set('category', params.category);
  if (params?.limit) qs.set('limit', String(params.limit));
  const q = qs.toString();

  return useQuery({
    queryKey: ['examples', params],
    queryFn: () => api.get<PagedResponse<ExampleItem>>(`/examples${q ? `?${q}` : ''}`),
  });
}

export function useExampleCategories() {
  return useQuery({
    queryKey: ['examples', 'categories'],
    queryFn: () => api.get<SuccessResponse<string[]>>('/examples/categories'),
  });
}

export function useExampleResults() {
  return useQuery({
    queryKey: ['examples', 'results'],
    queryFn: () => api.get<SuccessResponse<ExamplesSummary>>('/examples/results'),
    refetchInterval: 10_000,
  });
}

export function useExampleRunStatus() {
  return useQuery({
    queryKey: ['examples', 'run', 'status'],
    queryFn: () => api.get<SuccessResponse<RunExamplesResponse>>('/examples/run/status'),
    refetchInterval: 3_000,
  });
}

export function useRunExamples() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body?: { category?: string; timeout?: number }) =>
      api.post<RunExamplesResponse>('/examples/run', body ?? {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['examples', 'results'] });
      qc.invalidateQueries({ queryKey: ['examples', 'run', 'status'] });
    },
  });
}

export function useExampleSource(name: string) {
  return useQuery({
    queryKey: ['examples', 'source', name],
    queryFn: () => api.get<SuccessResponse<ExampleSource>>(`/examples/${name}/source`),
    enabled: !!name,
    staleTime: 5 * 60 * 1000, // source rarely changes; cache 5 min
  });
}

// ── Playground ──────────────────────────────────────────────────────

export function usePlaygroundWorkflows() {
  return useQuery({
    queryKey: ['playground', 'workflows'],
    queryFn: () => api.get<PagedResponse<PlaygroundWorkflow>>('/playground/workflows'),
  });
}

export function usePlaygroundExamples(category?: string) {
  const qs = category ? `?category=${encodeURIComponent(category)}` : '';
  return useQuery({
    queryKey: ['playground', 'examples', category],
    queryFn: () => api.get<PagedResponse<PlaygroundExample>>(`/playground/examples${qs}`),
  });
}

export function usePlaygroundSessions() {
  return useQuery({
    queryKey: ['playground', 'sessions'],
    queryFn: () => api.get<PagedResponse<PlaygroundSession>>('/playground/sessions'),
    refetchInterval: 5_000,
  });
}

export function usePlaygroundSession(sid: string) {
  return useQuery({
    queryKey: ['playground', 'sessions', sid],
    queryFn: () => api.get<SuccessResponse<PlaygroundSession>>(`/playground/sessions/${sid}`),
    enabled: !!sid,
    refetchInterval: 3_000,
  });
}

export function usePlaygroundContext(sid: string) {
  return useQuery({
    queryKey: ['playground', 'sessions', sid, 'context'],
    queryFn: () => api.get<SuccessResponse<ContextSnapshot>>(`/playground/sessions/${sid}/context`),
    enabled: !!sid,
  });
}

export function usePlaygroundHistory(sid: string) {
  return useQuery({
    queryKey: ['playground', 'sessions', sid, 'history'],
    queryFn: () => api.get<SuccessResponse<StepSnapshot[]>>(`/playground/sessions/${sid}/history`),
    enabled: !!sid,
  });
}

export function usePlaygroundPeek(sid: string) {
  return useQuery({
    queryKey: ['playground', 'sessions', sid, 'peek'],
    queryFn: () => api.get<SuccessResponse<StepPreview | null>>(`/playground/sessions/${sid}/peek`),
    enabled: !!sid,
  });
}

export function useCreatePlaygroundSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateSessionRequest) =>
      api.post<SuccessResponse<PlaygroundSession>>('/playground/sessions', body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['playground', 'sessions'] }),
  });
}

export function useDeletePlaygroundSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (sid: string) => api.del(`/playground/sessions/${sid}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['playground', 'sessions'] }),
  });
}

export function usePlaygroundStep() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (sid: string) =>
      api.post<SuccessResponse<StepSnapshot>>(`/playground/sessions/${sid}/step`),
    onSuccess: (_data, sid) => {
      qc.invalidateQueries({ queryKey: ['playground', 'sessions', sid] });
    },
  });
}

export function usePlaygroundStepBack() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (sid: string) =>
      api.post<SuccessResponse<StepSnapshot | null>>(`/playground/sessions/${sid}/step-back`),
    onSuccess: (_data, sid) => {
      qc.invalidateQueries({ queryKey: ['playground', 'sessions', sid] });
    },
  });
}

export function usePlaygroundRunAll() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (sid: string) =>
      api.post<SuccessResponse<StepSnapshot[]>>(`/playground/sessions/${sid}/run-all`),
    onSuccess: (_data, sid) => {
      qc.invalidateQueries({ queryKey: ['playground', 'sessions', sid] });
    },
  });
}

export function usePlaygroundRunTo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ sid, stepName }: { sid: string; stepName: string }) =>
      api.post<SuccessResponse<StepSnapshot[]>>(`/playground/sessions/${sid}/run-to`, { step_name: stepName }),
    onSuccess: (_data, { sid }) => {
      qc.invalidateQueries({ queryKey: ['playground', 'sessions', sid] });
    },
  });
}

export function usePlaygroundReset() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (sid: string) =>
      api.post<SuccessResponse<PlaygroundSession>>(`/playground/sessions/${sid}/reset`),
    onSuccess: (_data, sid) => {
      qc.invalidateQueries({ queryKey: ['playground', 'sessions', sid] });
    },
  });
}

export function usePlaygroundSetParams() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ sid, params }: { sid: string; params: Record<string, unknown> }) =>
      api.post(`/playground/sessions/${sid}/params`, { params }),
    onSuccess: (_data, { sid }) => {
      qc.invalidateQueries({ queryKey: ['playground', 'sessions', sid] });
    },
  });
}

// ── Functions ───────────────────────────────────────────────────────

export function useFunctions(params?: { tag?: string; search?: string; limit?: number }) {
  const qs = new URLSearchParams();
  if (params?.tag) qs.set('tag', params.tag);
  if (params?.search) qs.set('search', params.search);
  if (params?.limit) qs.set('limit', String(params.limit));
  const q = qs.toString();

  return useQuery({
    queryKey: ['functions', params],
    queryFn: () => api.get<PagedResponse<FunctionSummary>>(`/functions${q ? `?${q}` : ''}`),
    refetchInterval: 10_000,
    placeholderData: keepPreviousData,
  });
}

export function useFunction(functionId: string) {
  return useQuery({
    queryKey: ['functions', functionId],
    queryFn: () => api.get<SuccessResponse<FunctionDetail>>(`/functions/${functionId}`),
    enabled: !!functionId,
  });
}

export function useCreateFunction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: FunctionCreateRequest) =>
      api.post<SuccessResponse<FunctionDetail>>('/functions', body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['functions'] }),
  });
}

export function useUpdateFunction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: FunctionUpdateRequest }) =>
      api.put<SuccessResponse<FunctionDetail>>(`/functions/${id}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['functions'] }),
  });
}

export function useDeleteFunction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.del(`/functions/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['functions'] }),
  });
}

export function useInvokeFunction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body?: InvokeRequest }) =>
      api.post<SuccessResponse<InvokeResult>>(`/functions/${id}/invoke`, body ?? {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['functions'] }),
  });
}

export function useFunctionLogs(functionId: string, limit?: number) {
  const qs = limit ? `?limit=${limit}` : '';
  return useQuery({
    queryKey: ['functions', functionId, 'logs'],
    queryFn: () => api.get<SuccessResponse<InvocationLog[]>>(`/functions/${functionId}/logs${qs}`),
    enabled: !!functionId,
    refetchInterval: 5_000,
  });
}

export function useFunctionTemplates() {
  return useQuery({
    queryKey: ['functions', 'templates'],
    queryFn: () => api.get<SuccessResponse<FunctionTemplate[]>>('/functions/templates'),
    staleTime: 5 * 60 * 1000,
  });
}
