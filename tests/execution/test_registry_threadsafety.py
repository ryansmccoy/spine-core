"""Thread-safety tests for execution and framework registries.

Verifies that concurrent registration and lookup operations
do not corrupt state or raise errors.
"""

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from spine.execution.registry import HandlerRegistry


class TestHandlerRegistryThreadSafety:
    """Concurrent registration and retrieval tests for HandlerRegistry."""

    def test_concurrent_registration(self):
        """Multiple threads registering different handlers simultaneously."""
        registry = HandlerRegistry()
        errors = []

        def register_handler(i: int):
            try:
                registry.register(
                    kind="task",
                    name=f"handler_{i}",
                    handler=lambda: i,
                    description=f"Handler {i}",
                )
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(register_handler, i) for i in range(100)]
            for f in as_completed(futures):
                f.result()

        assert len(errors) == 0
        # All 100 handlers registered
        handlers = registry.list_handlers(kind="task")
        assert len(handlers) == 100

    def test_concurrent_read_write(self):
        """Readers and writers running simultaneously."""
        registry = HandlerRegistry()
        # Pre-populate
        for i in range(50):
            registry.register("task", f"init_{i}", lambda: i)

        errors = []
        results = []

        def writer(i: int):
            try:
                registry.register("task", f"new_{i}", lambda: i)
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                items = registry.list_handlers(kind="task")
                results.append(len(items))
            except Exception as e:
                errors.append(e)

        threads = []
        for i in range(50):
            threads.append(threading.Thread(target=writer, args=(i,)))
            threads.append(threading.Thread(target=reader))

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(errors) == 0
        # All results should be valid counts
        for count in results:
            assert 50 <= count <= 100

    def test_concurrent_get(self):
        """Many threads looking up the same handler."""
        registry = HandlerRegistry()
        registry.register("task", "shared", lambda: "ok")

        errors = []
        results = []

        def reader():
            try:
                h = registry.get("task", "shared")
                results.append(h())
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=reader) for _ in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(errors) == 0
        assert all(r == "ok" for r in results)

    def test_concurrent_unregister(self):
        """Concurrent unregister should not corrupt registry."""
        registry = HandlerRegistry()
        for i in range(100):
            registry.register("task", f"handler_{i}", lambda: i)

        errors = []

        def unregister(i: int):
            try:
                registry.unregister("task", f"handler_{i}")
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(unregister, i) for i in range(100)]
            for f in as_completed(futures):
                f.result()

        assert len(errors) == 0
        assert len(registry.list_handlers(kind="task")) == 0

    def test_concurrent_has_check(self):
        """Concurrent has() checks while registering."""
        registry = HandlerRegistry()
        errors = []

        def register_and_check(i: int):
            try:
                registry.register("task", f"h_{i}", lambda: i)
                assert registry.has("task", f"h_{i}")
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(register_and_check, i) for i in range(100)]
            for f in as_completed(futures):
                f.result()

        assert len(errors) == 0
