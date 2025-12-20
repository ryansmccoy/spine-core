"""Job Engine runtimes --- verbose deep-dive examples for every capability.

This category provides comprehensive, verbose examples that exercise every
parameter, edge case, and error path of the Job Engine runtimes subsystem.

Unlike the concise examples in `02_execution/` (which show the happy path),
these examples are designed to be **reference documentation** --- showing ALL
capabilities including current limitations.

NOTE: Several capabilities are planned but not yet implemented (see
`docs/architecture/WORKFLOW_PACKAGER_AUDIT.md` and
`docs/architecture/CONTAINER_EXECUTION_AUDIT.md` for gap analysis).
Examples here are honest about what works vs. what is planned.

CONTAINER JOB SPEC --- the universal job description
------------------------------------------------------
    01 --- ContainerJobSpec deep dive (all 30+ fields)
    02 --- Resource requirements, volumes, sidecars, init containers

RUNTIME ADAPTERS --- executing jobs
-------------------------------------
    03 --- LocalProcessAdapter full API (all params, edge cases)
    04 --- StubRuntimeAdapter for testing (injectable failures)

ENGINE AND ROUTING --- coordination layer
-------------------------------------------
    05 --- JobEngine full lifecycle (submit, status, cancel, logs, cleanup)
    06 --- RuntimeAdapterRouter (multi-runtime, health, routing)

VALIDATION AND ERRORS --- pre-flight and error handling
---------------------------------------------------------
    07 --- SpecValidator (all 3 validation layers)
    08 --- Error taxonomy (ErrorCategory, JobError, retryable)

PACKAGING --- workflow portability
------------------------------------
    09 --- WorkflowPackager (pack, inspect, unpack, limitations)
"""