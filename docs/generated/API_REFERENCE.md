# API Reference

**Public API Documentation**

*Auto-generated from code annotations on 2026-02-19*

---

## Table of Contents

- [spine.core.anomalies](#spinecoreanomalies)
- [spine.core.errors](#spinecoreerrors)
- [spine.core.execution](#spinecoreexecution)
- [spine.core.finance.adjustments](#spinecorefinanceadjustments)
- [spine.core.finance.corrections](#spinecorefinancecorrections)
- [spine.core.idempotency](#spinecoreidempotency)
- [spine.core.manifest](#spinecoremanifest)
- [spine.core.protocols](#spinecoreprotocols)
- [spine.core.quality](#spinecorequality)
- [spine.core.rejects](#spinecorerejects)
- [spine.core.result](#spinecoreresult)
- [spine.core.rolling](#spinecorerolling)
- [spine.core.storage](#spinecorestorage)
- [spine.core.temporal](#spinecoretemporal)
- [spine.core.temporal_envelope](#spinecoretemporal_envelope)
- [spine.core.watermarks](#spinecorewatermarks)
- [spine.domain.finance.enums](#spinedomainfinanceenums)
- [spine.domain.finance.observations](#spinedomainfinanceobservations)
- [spine.execution.executors.celery](#spineexecutionexecutorscelery)
- [spine.execution.executors.local](#spineexecutionexecutorslocal)
- [spine.execution.worker](#spineexecutionworker)
- [spine.orchestration.tracked_runner](#spineorchestrationtracked_runner)
- [spine.tools.changelog.generator](#spinetoolschangeloggenerator)
- [spine.tools.changelog.model](#spinetoolschangelogmodel)

---

## spine.core.anomalies

### `Severity`

*Defined in [B:\github\py-sec-edgar\spine-core\src\spine\core\anomalies.py](B:\github\py-sec-edgar\spine-core\src\spine\core\anomalies.py#L123)*

### `AnomalyCategory`

*Defined in [B:\github\py-sec-edgar\spine-core\src\spine\core\anomalies.py](B:\github\py-sec-edgar\spine-core\src\spine\core\anomalies.py#L176)*

### `AnomalyRecorder`

*Defined in [B:\github\py-sec-edgar\spine-core\src\spine\core\anomalies.py](B:\github\py-sec-edgar\spine-core\src\spine\core\anomalies.py#L241)*

## spine.core.errors

### `ErrorCategory`

*Defined in [B:\github\py-sec-edgar\spine-core\src\spine\core\errors.py](B:\github\py-sec-edgar\spine-core\src\spine\core\errors.py#L142)*

### `ErrorContext`

*Defined in [B:\github\py-sec-edgar\spine-core\src\spine\core\errors.py](B:\github\py-sec-edgar\spine-core\src\spine\core\errors.py#L253)*

### `SpineError`

*Defined in [B:\github\py-sec-edgar\spine-core\src\spine\core\errors.py](B:\github\py-sec-edgar\spine-core\src\spine\core\errors.py#L387)*

### `TransientError`

*Defined in [B:\github\py-sec-edgar\spine-core\src\spine\core\errors.py](B:\github\py-sec-edgar\spine-core\src\spine\core\errors.py#L598)*

## spine.core.execution

### `ExecutionContext`

*Defined in [B:\github\py-sec-edgar\spine-core\src\spine\core\execution.py](B:\github\py-sec-edgar\spine-core\src\spine\core\execution.py#L121)*

## spine.core.finance.adjustments

### `AdjustmentFactor`

*Defined in [B:\github\py-sec-edgar\spine-core\src\spine\core\finance\adjustments.py](B:\github\py-sec-edgar\spine-core\src\spine\core\finance\adjustments.py#L120)*

### `AdjustmentChain`

*Defined in [B:\github\py-sec-edgar\spine-core\src\spine\core\finance\adjustments.py](B:\github\py-sec-edgar\spine-core\src\spine\core\finance\adjustments.py#L171)*

## spine.core.finance.corrections

### `CorrectionRecord`

*Defined in [B:\github\py-sec-edgar\spine-core\src\spine\core\finance\corrections.py](B:\github\py-sec-edgar\spine-core\src\spine\core\finance\corrections.py#L135)*

## spine.core.idempotency

### `IdempotencyLevel`

*Defined in [B:\github\py-sec-edgar\spine-core\src\spine\core\idempotency.py](B:\github\py-sec-edgar\spine-core\src\spine\core\idempotency.py#L78)*

### `IdempotencyHelper`

*Defined in [B:\github\py-sec-edgar\spine-core\src\spine\core\idempotency.py](B:\github\py-sec-edgar\spine-core\src\spine\core\idempotency.py#L156)*

### `LogicalKey`

*Defined in [B:\github\py-sec-edgar\spine-core\src\spine\core\idempotency.py](B:\github\py-sec-edgar\spine-core\src\spine\core\idempotency.py#L286)*

## spine.core.manifest

### `ManifestRow`

*Defined in [B:\github\py-sec-edgar\spine-core\src\spine\core\manifest.py](B:\github\py-sec-edgar\spine-core\src\spine\core\manifest.py#L140)*

### `WorkManifest`

*Defined in [B:\github\py-sec-edgar\spine-core\src\spine\core\manifest.py](B:\github\py-sec-edgar\spine-core\src\spine\core\manifest.py#L223)*

## spine.core.protocols

### `Connection`

*Defined in [B:\github\py-sec-edgar\spine-core\src\spine\core\protocols.py](B:\github\py-sec-edgar\spine-core\src\spine\core\protocols.py#L84)*

### `AsyncConnection`

*Defined in [B:\github\py-sec-edgar\spine-core\src\spine\core\protocols.py](B:\github\py-sec-edgar\spine-core\src\spine\core\protocols.py#L164)*

### `DispatcherProtocol`

*Defined in [B:\github\py-sec-edgar\spine-core\src\spine\core\protocols.py](B:\github\py-sec-edgar\spine-core\src\spine\core\protocols.py#L216)*

### `OperationProtocol`

*Defined in [B:\github\py-sec-edgar\spine-core\src\spine\core\protocols.py](B:\github\py-sec-edgar\spine-core\src\spine\core\protocols.py#L236)*

### `ExecutorProtocol`

*Defined in [B:\github\py-sec-edgar\spine-core\src\spine\core\protocols.py](B:\github\py-sec-edgar\spine-core\src\spine\core\protocols.py#L258)*

## spine.core.quality

### `QualityStatus`

*Defined in [B:\github\py-sec-edgar\spine-core\src\spine\core\quality.py](B:\github\py-sec-edgar\spine-core\src\spine\core\quality.py#L128)*

### `QualityCategory`

*Defined in [B:\github\py-sec-edgar\spine-core\src\spine\core\quality.py](B:\github\py-sec-edgar\spine-core\src\spine\core\quality.py#L155)*

### `QualityResult`

*Defined in [B:\github\py-sec-edgar\spine-core\src\spine\core\quality.py](B:\github\py-sec-edgar\spine-core\src\spine\core\quality.py#L185)*

### `QualityCheck`

*Defined in [B:\github\py-sec-edgar\spine-core\src\spine\core\quality.py](B:\github\py-sec-edgar\spine-core\src\spine\core\quality.py#L237)*

### `QualityRunner`

*Defined in [B:\github\py-sec-edgar\spine-core\src\spine\core\quality.py](B:\github\py-sec-edgar\spine-core\src\spine\core\quality.py#L281)*

## spine.core.rejects

### `Reject`

*Defined in [B:\github\py-sec-edgar\spine-core\src\spine\core\rejects.py](B:\github\py-sec-edgar\spine-core\src\spine\core\rejects.py#L130)*

### `RejectSink`

*Defined in [B:\github\py-sec-edgar\spine-core\src\spine\core\rejects.py](B:\github\py-sec-edgar\spine-core\src\spine\core\rejects.py#L195)*

## spine.core.result

### `Ok`

*Defined in [B:\github\py-sec-edgar\spine-core\src\spine\core\result.py](B:\github\py-sec-edgar\spine-core\src\spine\core\result.py#L140)*

### `Err`

*Defined in [B:\github\py-sec-edgar\spine-core\src\spine\core\result.py](B:\github\py-sec-edgar\spine-core\src\spine\core\result.py#L299)*

## spine.core.rolling

### `RollingResult`

*Defined in [B:\github\py-sec-edgar\spine-core\src\spine\core\rolling.py](B:\github\py-sec-edgar\spine-core\src\spine\core\rolling.py#L89)*

### `RollingWindow`

*Defined in [B:\github\py-sec-edgar\spine-core\src\spine\core\rolling.py](B:\github\py-sec-edgar\spine-core\src\spine\core\rolling.py#L178)*

## spine.core.storage

### `StorageBackend`

*Defined in [B:\github\py-sec-edgar\spine-core\src\spine\core\storage.py](B:\github\py-sec-edgar\spine-core\src\spine\core\storage.py#L115)*

## spine.core.temporal

### `WeekEnding`

*Defined in [B:\github\py-sec-edgar\spine-core\src\spine\core\temporal.py](B:\github\py-sec-edgar\spine-core\src\spine\core\temporal.py#L72)*

## spine.core.temporal_envelope

### `TemporalEnvelope`

*Defined in [B:\github\py-sec-edgar\spine-core\src\spine\core\temporal_envelope.py](B:\github\py-sec-edgar\spine-core\src\spine\core\temporal_envelope.py#L107)*

## spine.core.watermarks

### `WatermarkStore`

*Defined in [B:\github\py-sec-edgar\spine-core\src\spine\core\watermarks.py](B:\github\py-sec-edgar\spine-core\src\spine\core\watermarks.py#L159)*

## spine.domain.finance.enums

### `PeriodType`

*Defined in [B:\github\py-sec-edgar\spine-core\src\spine\domain\finance\enums.py](B:\github\py-sec-edgar\spine-core\src\spine\domain\finance\enums.py#L232)*

## spine.domain.finance.observations

### `FiscalPeriod`

*Defined in [B:\github\py-sec-edgar\spine-core\src\spine\domain\finance\observations.py](B:\github\py-sec-edgar\spine-core\src\spine\domain\finance\observations.py#L198)*

## spine.execution.executors.celery

### `CeleryExecutor`

*Defined in [B:\github\py-sec-edgar\spine-core\src\spine\execution\executors\celery.py](B:\github\py-sec-edgar\spine-core\src\spine\execution\executors\celery.py#L56)*

## spine.execution.executors.local

### `LocalExecutor`

*Defined in [B:\github\py-sec-edgar\spine-core\src\spine\execution\executors\local.py](B:\github\py-sec-edgar\spine-core\src\spine\execution\executors\local.py#L39)*

## spine.execution.worker

### `WorkerLoop`

*Defined in [B:\github\py-sec-edgar\spine-core\src\spine\execution\worker.py](B:\github\py-sec-edgar\spine-core\src\spine\execution\worker.py#L131)*

## spine.orchestration.tracked_runner

### `TrackedWorkflowRunner`

*Defined in [B:\github\py-sec-edgar\spine-core\src\spine\orchestration\tracked_runner.py](B:\github\py-sec-edgar\spine-core\src\spine\orchestration\tracked_runner.py#L83)*

## spine.tools.changelog.generator

### `ChangelogGenerator`

*Defined in [B:\github\py-sec-edgar\spine-core\src\spine\tools\changelog\generator.py](B:\github\py-sec-edgar\spine-core\src\spine\tools\changelog\generator.py#L59)*

## spine.tools.changelog.model

### `DocHeader`

*Defined in [B:\github\py-sec-edgar\spine-core\src\spine\tools\changelog\model.py](B:\github\py-sec-edgar\spine-core\src\spine\tools\changelog\model.py#L118)*


---

*44 classes across 24 modules*

*Generated by [doc-automation](https://github.com/your-org/py-sec-edgar/tree/main/spine-core/packages/doc-automation)*