# spine.orchestration

The workflow orchestration layer — building, running, tracking, and composing multi-step data pipelines.

## Key Modules

| Module | Purpose |
|--------|---------|
| `workflow` | `Workflow`, `Step` — DAG definitions |
| `step_types` | `lambda_step()`, `operation_step()`, `function_step()` |
| `step_result` | `StepResult` with output data and quality metrics |
| `workflow_runner` | `WorkflowRunner` — sequential/parallel execution |
| `tracked_runner` | `TrackedWorkflowRunner` — database-backed with checkpoints |
| `workflow_context` | `WorkflowContext` — step-to-step data passing |
| `composition` | `chain()`, `parallel()`, `conditional()`, `merge_workflows()` |
| `templates` | `etl_operation()`, `fan_out_fan_in()`, `retry_wrapper()` |
| `playground` | `WorkflowPlayground` — interactive step debugger |
| `recorder` | `WorkflowRecording`, `RecordingRunner` — capture and replay |
| `managed_workflow` | `manage(wf).with_tracking().with_retry().build()` |
| `linter` | `lint_workflow()` — static analysis |
| `visualizer` | `visualize_mermaid()`, `visualize_ascii()` |
| `dry_run` | `dry_run()` — simulate without side effects |
| `workflow_yaml` | YAML workflow loading and validation |
| `llm/` | `LLMProvider`, `LLMRouter`, `TokenBudget` |

## Workflow Execution Flow

```
Define workflow (code or YAML)
    │
    ▼
WorkflowRunner.run(workflow)
    │
    ├─→ Step 1: extract   → StepResult(data=...)
    ├─→ Step 2: transform → StepResult(data=...)
    └─→ Step 3: load      → StepResult(data=...)
    │
    ▼
WorkflowResult (all step results + timing)
```

## API Reference

See the full auto-generated API docs at [API Reference — spine.orchestration](../api/orchestration.md).
