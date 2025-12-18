"""Tests for RuntimeAdapterRouter — adapter registry and routing.

Tests:
    - Registration and auto-default
    - Explicit routing by spec.runtime
    - Default routing when spec.runtime is None
    - Error cases (no adapters, unknown runtime)
    - Unregister
    - health_all()
    - List runtimes
"""

import pytest

from spine.execution.runtimes._types import (
    ContainerJobSpec,
    ErrorCategory,
    JobError,
    RuntimeCapabilities,
    RuntimeHealth,
)
from spine.execution.runtimes._base import StubRuntimeAdapter
from spine.execution.runtimes.router import RuntimeAdapterRouter


@pytest.fixture
def router():
    return RuntimeAdapterRouter()


@pytest.fixture
def stub_adapter():
    return StubRuntimeAdapter()


@pytest.fixture
def minimal_spec():
    return ContainerJobSpec(name="test-job", image="alpine:latest")


class _NamedStubAdapter(StubRuntimeAdapter):
    """StubRuntimeAdapter with a configurable runtime_name."""

    def __init__(self, name: str = "stub", **kwargs):
        super().__init__(**kwargs)
        self._name = name

    @property
    def runtime_name(self) -> str:
        return self._name


class TestRegistration:
    """Test adapter registration."""

    def test_register_adapter(self, router, stub_adapter):
        router.register(stub_adapter)
        assert "stub" in router
        assert len(router) == 1

    def test_auto_default_on_first_register(self, router, stub_adapter):
        router.register(stub_adapter)
        assert router.default_name == "stub"

    def test_second_register_does_not_change_default(self, router):
        router.register(_NamedStubAdapter("docker"))
        router.register(_NamedStubAdapter("k8s"))
        assert router.default_name == "docker"

    def test_replace_existing_adapter(self, router):
        adapter1 = _NamedStubAdapter("docker")
        adapter2 = _NamedStubAdapter("docker")
        router.register(adapter1)
        router.register(adapter2)
        assert len(router) == 1
        assert router.get("docker") is adapter2

    def test_list_runtimes_sorted(self, router):
        router.register(_NamedStubAdapter("k8s"))
        router.register(_NamedStubAdapter("docker"))
        router.register(_NamedStubAdapter("ecs"))
        assert router.list_runtimes() == ["docker", "ecs", "k8s"]

    def test_get_nonexistent(self, router):
        assert router.get("nonexistent") is None


class TestUnregister:
    """Test adapter unregistration."""

    def test_unregister_existing(self, router, stub_adapter):
        router.register(stub_adapter)
        result = router.unregister("stub")
        assert result is True
        assert "stub" not in router
        assert len(router) == 0

    def test_unregister_clears_default(self, router, stub_adapter):
        router.register(stub_adapter)
        assert router.default_name == "stub"
        router.unregister("stub")
        assert router.default_name is None

    def test_unregister_nonexistent(self, router):
        result = router.unregister("nonexistent")
        assert result is False


class TestSetDefault:
    """Test explicit default setting."""

    def test_set_default(self, router):
        router.register(_NamedStubAdapter("docker"))
        router.register(_NamedStubAdapter("k8s"))
        router.set_default("k8s")
        assert router.default_name == "k8s"

    def test_set_default_nonexistent_raises(self, router):
        with pytest.raises(JobError) as exc_info:
            router.set_default("nonexistent")
        assert exc_info.value.category == ErrorCategory.NOT_FOUND


class TestRouting:
    """Test spec routing."""

    def test_route_explicit_runtime(self, router, minimal_spec):
        docker = _NamedStubAdapter("docker")
        k8s = _NamedStubAdapter("k8s")
        router.register(docker)
        router.register(k8s)

        minimal_spec.runtime = "k8s"
        adapter = router.route(minimal_spec)
        assert adapter is k8s

    def test_route_to_default_when_no_runtime(self, router, minimal_spec):
        docker = _NamedStubAdapter("docker")
        router.register(docker)

        assert minimal_spec.runtime is None
        adapter = router.route(minimal_spec)
        assert adapter is docker

    def test_route_unknown_runtime_raises(self, router, minimal_spec):
        router.register(_NamedStubAdapter("docker"))
        minimal_spec.runtime = "lambda"
        with pytest.raises(JobError) as exc_info:
            router.route(minimal_spec)
        assert exc_info.value.category == ErrorCategory.NOT_FOUND
        assert "lambda" in exc_info.value.message
        assert "docker" in exc_info.value.message  # Available runtimes listed

    def test_route_no_adapters_raises(self, router, minimal_spec):
        with pytest.raises(JobError) as exc_info:
            router.route(minimal_spec)
        assert exc_info.value.category == ErrorCategory.NOT_FOUND
        assert "No runtime adapters registered" in exc_info.value.message

    def test_route_no_default_but_has_adapters_raises(self, router, minimal_spec):
        """Adapters exist but default was cleared."""
        router.register(_NamedStubAdapter("docker"))
        router.unregister("docker")
        router.register(_NamedStubAdapter("k8s"))
        # Default was cleared when docker was unregistered
        # k8s was registered after, but since default was already None
        # and k8s is not the first (default_name was already set to None),
        # let's verify: actually, since _default_name is None and k8s registers,
        # auto-default kicks in. Let's set up differently.
        router2 = RuntimeAdapterRouter()
        a = _NamedStubAdapter("k8s")
        router2.register(a)
        router2._default_name = None  # Manually clear for edge case
        with pytest.raises(JobError) as exc_info:
            router2.route(minimal_spec)
        assert "No default runtime set" in exc_info.value.message


class TestHealthAll:
    """Test health_all()."""

    @pytest.mark.asyncio
    async def test_health_all_healthy(self, router):
        router.register(_NamedStubAdapter("docker"))
        router.register(_NamedStubAdapter("k8s"))
        results = await router.health_all()
        assert len(results) == 2
        assert results["docker"].healthy
        assert results["k8s"].healthy

    @pytest.mark.asyncio
    async def test_health_all_includes_unhealthy(self, router):
        healthy = _NamedStubAdapter("docker")
        unhealthy = _NamedStubAdapter("k8s")
        unhealthy.fail_health = True
        router.register(healthy)
        router.register(unhealthy)
        results = await router.health_all()
        assert results["docker"].healthy
        assert not results["k8s"].healthy

    @pytest.mark.asyncio
    async def test_health_all_empty(self, router):
        results = await router.health_all()
        assert results == {}


class TestRepr:
    """Test string representation."""

    def test_repr_empty(self, router):
        assert "RuntimeAdapterRouter" in repr(router)

    def test_repr_with_adapters(self, router):
        router.register(_NamedStubAdapter("docker"))
        r = repr(router)
        assert "docker" in r
        assert "default=docker" in r

    def test_contains(self, router, stub_adapter):
        router.register(stub_adapter)
        assert "stub" in router
        assert "nonexistent" not in router

    def test_len(self, router):
        assert len(router) == 0
        router.register(_NamedStubAdapter("a"))
        router.register(_NamedStubAdapter("b"))
        assert len(router) == 2
