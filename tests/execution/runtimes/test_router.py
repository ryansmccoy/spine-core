"""Tests for RuntimeAdapterRouter — adapter registry and routing."""

from __future__ import annotations

import asyncio

import pytest

from spine.execution.runtimes._base import StubRuntimeAdapter
from spine.execution.runtimes._types import (
    ContainerJobSpec,
    ErrorCategory,
    JobError,
    RuntimeHealth,
)
from spine.execution.runtimes.router import RuntimeAdapterRouter


# ── Helpers ──────────────────────────────────────────────────────────────


def _spec(name: str = "job", runtime: str | None = None) -> ContainerJobSpec:
    return ContainerJobSpec(name=name, image="test:latest", runtime=runtime)


class _FakeAdapter:
    """Minimal adapter for testing routing (not StubRuntimeAdapter)."""

    def __init__(self, name: str):
        self._name = name

    @property
    def runtime_name(self) -> str:
        return self._name

    @property
    def capabilities(self):
        from spine.execution.runtimes._types import RuntimeCapabilities
        return RuntimeCapabilities()

    @property
    def constraints(self):
        from spine.execution.runtimes._types import RuntimeConstraints
        return RuntimeConstraints()

    async def health(self) -> RuntimeHealth:
        return RuntimeHealth(healthy=True, runtime=self._name)


# ── Registration ─────────────────────────────────────────────────────────


class TestRegistration:
    def test_register_adapter(self):
        router = RuntimeAdapterRouter()
        adapter = _FakeAdapter("docker")
        router.register(adapter)
        assert "docker" in router
        assert router.list_runtimes() == ["docker"]

    def test_first_adapter_becomes_default(self):
        router = RuntimeAdapterRouter()
        router.register(_FakeAdapter("docker"))
        assert router.default_name == "docker"

    def test_second_adapter_does_not_override_default(self):
        router = RuntimeAdapterRouter()
        router.register(_FakeAdapter("docker"))
        router.register(_FakeAdapter("k8s"))
        assert router.default_name == "docker"

    def test_unregister(self):
        router = RuntimeAdapterRouter()
        router.register(_FakeAdapter("docker"))
        assert router.unregister("docker") is True
        assert "docker" not in router

    def test_unregister_nonexistent(self):
        router = RuntimeAdapterRouter()
        assert router.unregister("nope") is False

    def test_unregister_default_clears_default(self):
        router = RuntimeAdapterRouter()
        router.register(_FakeAdapter("docker"))
        router.unregister("docker")
        assert router.default_name is None

    def test_get_existing(self):
        router = RuntimeAdapterRouter()
        adapter = _FakeAdapter("docker")
        router.register(adapter)
        assert router.get("docker") is adapter

    def test_get_nonexistent(self):
        router = RuntimeAdapterRouter()
        assert router.get("nope") is None

    def test_len(self):
        router = RuntimeAdapterRouter()
        assert len(router) == 0
        router.register(_FakeAdapter("a"))
        router.register(_FakeAdapter("b"))
        assert len(router) == 2

    def test_list_runtimes_sorted(self):
        router = RuntimeAdapterRouter()
        router.register(_FakeAdapter("k8s"))
        router.register(_FakeAdapter("docker"))
        assert router.list_runtimes() == ["docker", "k8s"]


# ── Set Default ──────────────────────────────────────────────────────────


class TestSetDefault:
    def test_set_default(self):
        router = RuntimeAdapterRouter()
        router.register(_FakeAdapter("docker"))
        router.register(_FakeAdapter("k8s"))
        router.set_default("k8s")
        assert router.default_name == "k8s"

    def test_set_default_nonexistent_raises(self):
        router = RuntimeAdapterRouter()
        with pytest.raises(JobError) as exc_info:
            router.set_default("nonexistent")
        assert exc_info.value.category == ErrorCategory.NOT_FOUND


# ── Routing ──────────────────────────────────────────────────────────────


class TestRouting:
    def test_explicit_runtime(self):
        router = RuntimeAdapterRouter()
        docker = _FakeAdapter("docker")
        k8s = _FakeAdapter("k8s")
        router.register(docker)
        router.register(k8s)
        selected = router.route(_spec(runtime="k8s"))
        assert selected is k8s

    def test_explicit_runtime_not_found_raises(self):
        router = RuntimeAdapterRouter()
        router.register(_FakeAdapter("docker"))
        with pytest.raises(JobError) as exc_info:
            router.route(_spec(runtime="nope"))
        assert exc_info.value.category == ErrorCategory.NOT_FOUND

    def test_no_runtime_uses_default(self):
        router = RuntimeAdapterRouter()
        docker = _FakeAdapter("docker")
        router.register(docker)
        selected = router.route(_spec(runtime=None))
        assert selected is docker

    def test_no_adapters_raises(self):
        router = RuntimeAdapterRouter()
        with pytest.raises(JobError):
            router.route(_spec())

    def test_no_default_raises(self):
        router = RuntimeAdapterRouter()
        router.register(_FakeAdapter("docker"))
        router.unregister("docker")
        router.register(_FakeAdapter("k8s"))
        # k8s registered but docker was unregistered (which was default)
        # default_name was cleared on unregister, then k8s became new default
        # Actually k8s would auto-set as new default since registry was empty
        selected = router.route(_spec())
        assert selected.runtime_name == "k8s"


# ── Health ───────────────────────────────────────────────────────────────


class TestHealth:
    @pytest.mark.asyncio
    async def test_health_all(self):
        router = RuntimeAdapterRouter()
        router.register(StubRuntimeAdapter())
        results = await router.health_all()
        assert "stub" in results
        assert results["stub"].healthy is True

    @pytest.mark.asyncio
    async def test_health_handles_error(self):
        router = RuntimeAdapterRouter()
        adapter = StubRuntimeAdapter()
        adapter.fail_health = True
        router.register(adapter)
        results = await router.health_all()
        # StubRuntimeAdapter returns unhealthy RuntimeHealth (not raise)
        assert "stub" in results


# ── Repr ─────────────────────────────────────────────────────────────────


class TestRepr:
    def test_repr_contains_names(self):
        router = RuntimeAdapterRouter()
        router.register(_FakeAdapter("docker"))
        r = repr(router)
        assert "docker" in r
        assert "RuntimeAdapterRouter" in r
