"""Stub Executor — no-op executor for testing and dry-run.

WHY
───
Sometimes you want to test dispatcher logic, validate WorkSpec
routing, or run in dry-run mode without actually executing any
work.  ``StubExecutor`` always succeeds immediately — the simplest
possible ``Executor`` implementation.

ARCHITECTURE
────────────
::

    StubExecutor()
      ├── .submit(spec)     ─ return ref immediately
      ├── .get_status(ref)  ─ always “completed”
      └── .cancel(ref)      ─ no-op

Related modules:
    protocol.py  — Executor protocol
    memory.py    — actually runs handlers (richer testing)
"""

import uuid

from ..spec import WorkSpec


class StubExecutor:
    """No-op executor for testing.

    Always succeeds immediately without actually executing anything.
    Useful for:
    - Integration tests (test dispatcher without real execution)
    - Unit tests (isolate from executor implementation)
    - Dry-run mode (validate specs without running)
    - Development (fast iteration without waiting)

    Example:
        >>> executor = StubExecutor()
        >>> ref = await executor.submit(task_spec("anything", {}))
        >>> status = await executor.get_status(ref)  # "completed"
    """

    def __init__(self):
        """Initialize stub executor."""
        self._name = "stub"
        self._submitted: list[WorkSpec] = []  # Track submissions for assertions

    @property
    def name(self) -> str:
        """Executor name for tracking."""
        return self._name

    async def submit(self, spec: WorkSpec) -> str:
        """Return fake external_ref without executing.

        Stores the spec for later inspection in tests.
        """
        self._submitted.append(spec)
        return f"stub-{uuid.uuid4().hex[:8]}"

    async def cancel(self, external_ref: str) -> bool:
        """Always succeeds (no-op)."""
        return True

    async def get_status(self, external_ref: str) -> str | None:
        """Always reports completed."""
        return "completed"

    # === TEST HELPERS ===

    @property
    def submitted_specs(self) -> list[WorkSpec]:
        """Get all specs that were submitted (for test assertions)."""
        return self._submitted.copy()

    @property
    def submission_count(self) -> int:
        """Get count of submissions (for test assertions)."""
        return len(self._submitted)

    def clear(self) -> None:
        """Clear submission history (for test cleanup)."""
        self._submitted.clear()

    def assert_submitted(self, kind: str, name: str) -> WorkSpec | None:
        """Assert a spec was submitted and return it.

        Args:
            kind: Expected work kind
            name: Expected work name

        Returns:
            The submitted spec if found

        Raises:
            AssertionError: If no matching spec was submitted
        """
        for spec in self._submitted:
            if spec.kind == kind and spec.name == name:
                return spec
        raise AssertionError(f"No {kind}:{name} was submitted. Got: {[(s.kind, s.name) for s in self._submitted]}")
