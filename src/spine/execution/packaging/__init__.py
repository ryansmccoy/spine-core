"""
Workflow Packaging — portable, self-contained workflow archives.

This module provides ``WorkflowPackager`` for bundling a
:class:`~spine.orchestration.workflow.Workflow` into a standalone
``.pyz`` archive (PEP 441) that can be executed with a bare
``python workflow.pyz`` command.

Architecture::

    ┌─────────────────┐
    │  WorkflowPackager│
    │                  │
    │  .package()  ────┼──► myworkflow.pyz
    │  .inspect()  ────┼──► PackageManifest
    │  .unpack()   ────┼──► directory tree
    └─────────────────┘

Key design constraints:

- **Pipeline steps** are stored by name (string).  The target
  environment must have the referenced pipelines installed.
- **Lambda steps** with *named* functions can be packaged by
  extracting their source via ``inspect.getsource()``.  Inline
  lambdas and closures are **not** portable — the packager
  emits a warning and skips them.
- **Choice / wait / map** steps are serialized via ``Step.to_dict()``
  and reconstructed on the other side.

Usage::

    from spine.orchestration import Workflow, Step
    from spine.execution.packaging import WorkflowPackager

    wf = Workflow(
        name="my.pipeline",
        steps=[
            Step.pipeline("ingest", "my.ingest"),
            Step.pipeline("transform", "my.transform"),
        ],
    )

    packager = WorkflowPackager()
    path = packager.package(wf, "my_pipeline.pyz")
    print(f"Created {path}  ({path.stat().st_size} bytes)")
"""

from spine.execution.packaging.packager import (
    PackageManifest,
    PackageWarning,
    WorkflowPackager,
)

__all__ = [
    "PackageManifest",
    "PackageWarning",
    "WorkflowPackager",
]
