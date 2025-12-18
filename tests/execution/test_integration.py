"""Integration tests for unified execution contract."""
import pytest
import asyncio
from spine.execution import (
    EventDispatcher,
    WorkSpec,
    task_spec,
    pipeline_spec,
    workflow_spec,
    step_spec,
    register_task,
    register_pipeline,
    HandlerRegistry,
    RunStatus,
    EventType,
)
from spine.execution.executors import MemoryExecutor, StubExecutor, LocalExecutor


class TestWorkSpec:
    """Test WorkSpec creation and convenience constructors."""
    
    def test_task_spec_minimal(self):
        """Test task_spec with minimal args."""
        spec = task_spec("send_email")
        assert spec.kind == "task"
        assert spec.name == "send_email"
        assert spec.params == {}
        assert spec.priority == "normal"
    
    def test_task_spec_with_params(self):
        """Test task_spec with params and kwargs."""
        spec = task_spec(
            "send_email",
            {"to": "user@example.com"},
            priority="high",
            idempotency_key="email-123",
        )
        assert spec.kind == "task"
        assert spec.name == "send_email"
        assert spec.params == {"to": "user@example.com"}
        assert spec.priority == "high"
        assert spec.idempotency_key == "email-123"
    
    def test_pipeline_spec(self):
        """Test pipeline_spec convenience."""
        spec = pipeline_spec("ingest_otc", {"date": "2026-01-15"})
        assert spec.kind == "pipeline"
        assert spec.name == "ingest_otc"
        assert spec.params == {"date": "2026-01-15"}
    
    def test_workflow_spec(self):
        """Test workflow_spec convenience."""
        spec = workflow_spec("daily_ingest", {"tier": "NMS"})
        assert spec.kind == "workflow"
        assert spec.name == "daily_ingest"
    
    def test_step_spec_with_parent(self):
        """Test step_spec with parent_run_id."""
        spec = step_spec("validate", {"data": []}, parent_run_id="parent-123")
        assert spec.kind == "step"
        assert spec.name == "validate"
        assert spec.parent_run_id == "parent-123"
        assert spec.correlation_id == "parent-123"


class TestHandlerRegistry:
    """Test HandlerRegistry functionality."""
    
    def test_register_and_get(self):
        """Test basic registration and retrieval."""
        registry = HandlerRegistry()
        
        def my_handler(params):
            return {"result": "ok"}
        
        registry.register("task", "test_task", my_handler)
        
        handler = registry.get("task", "test_task")
        assert handler == my_handler
    
    def test_register_via_decorator(self):
        """Test decorator-based registration."""
        registry = HandlerRegistry()
        
        @register_task("decorated_task", registry=registry)
        def decorated_handler(params):
            return params
        
        assert registry.has("task", "decorated_task")
        handler = registry.get("task", "decorated_task")
        assert handler({"x": 1}) == {"x": 1}
    
    def test_get_nonexistent_raises(self):
        """Test that getting missing handler raises ValueError."""
        registry = HandlerRegistry()
        
        with pytest.raises(ValueError, match="No handler registered"):
            registry.get("task", "nonexistent")
    
    def test_list_handlers(self):
        """Test listing handlers."""
        registry = HandlerRegistry()
        registry.register("task", "task1", lambda p: p)
        registry.register("task", "task2", lambda p: p)
        registry.register("pipeline", "pipe1", lambda p: p)
        
        all_handlers = registry.list_handlers()
        assert len(all_handlers) == 3
        
        task_handlers = registry.list_handlers(kind="task")
        assert len(task_handlers) == 2
        assert all(k == "task" for k, n in task_handlers)
    
    def test_to_executor_handlers(self):
        """Test conversion to executor handler dict."""
        registry = HandlerRegistry()
        registry.register("task", "t1", lambda p: p)
        registry.register("pipeline", "p1", lambda p: p)
        
        handlers = registry.to_executor_handlers()
        assert "task:t1" in handlers
        assert "pipeline:p1" in handlers


class TestMemoryExecutor:
    """Test MemoryExecutor functionality."""
    
    @pytest.mark.asyncio
    async def test_submit_and_get_status(self):
        """Test basic submit and status check."""
        handlers = {"task:test": lambda p: {"value": p["x"] * 2}}
        executor = MemoryExecutor(handlers)
        
        ref = await executor.submit(task_spec("test", {"x": 21}))
        status = await executor.get_status(ref)
        result = await executor.get_result(ref)
        
        assert status == "completed"
        assert result == {"value": 42}
    
    @pytest.mark.asyncio
    async def test_missing_handler_fails(self):
        """Test that missing handler results in failed status."""
        executor = MemoryExecutor()
        
        ref = await executor.submit(task_spec("nonexistent", {}))
        status = await executor.get_status(ref)
        error = await executor.get_error(ref)
        
        assert status == "failed"
        assert "No handler" in error
    
    @pytest.mark.asyncio
    async def test_handler_exception_fails(self):
        """Test that handler exception results in failed status."""
        def failing_handler(p):
            raise ValueError("Test error")
        
        executor = MemoryExecutor({"task:fail": failing_handler})
        
        ref = await executor.submit(task_spec("fail", {}))
        status = await executor.get_status(ref)
        error = await executor.get_error(ref)
        
        assert status == "failed"
        assert "Test error" in error
    
    @pytest.mark.asyncio
    async def test_async_handler(self):
        """Test async handler execution."""
        async def async_handler(p):
            await asyncio.sleep(0.01)
            return {"async": True}
        
        executor = MemoryExecutor({"task:async_test": async_handler})
        
        ref = await executor.submit(task_spec("async_test", {}))
        result = await executor.get_result(ref)
        
        assert result == {"async": True}


class TestStubExecutor:
    """Test StubExecutor functionality."""
    
    @pytest.mark.asyncio
    async def test_always_succeeds(self):
        """Test that stub always reports success."""
        executor = StubExecutor()
        
        ref = await executor.submit(task_spec("anything", {}))
        status = await executor.get_status(ref)
        
        assert status == "completed"
        assert ref.startswith("stub-")
    
    @pytest.mark.asyncio
    async def test_tracks_submissions(self):
        """Test that stub tracks submissions for assertions."""
        executor = StubExecutor()
        
        await executor.submit(task_spec("task1", {"x": 1}))
        await executor.submit(pipeline_spec("pipe1", {"y": 2}))
        
        assert executor.submission_count == 2
        
        spec = executor.assert_submitted("task", "task1")
        assert spec.params == {"x": 1}
    
    @pytest.mark.asyncio
    async def test_assert_submitted_fails_if_missing(self):
        """Test that assert_submitted raises if not found."""
        executor = StubExecutor()
        
        await executor.submit(task_spec("task1", {}))
        
        with pytest.raises(AssertionError, match="No pipeline:missing"):
            executor.assert_submitted("pipeline", "missing")


class TestDispatcher:
    """Test EventDispatcher functionality."""
    
    @pytest.mark.asyncio
    async def test_submit_and_get_run(self):
        """Test basic submit and retrieval."""
        executor = StubExecutor()
        dispatcher = EventDispatcher(executor=executor)
        
        run_id = await dispatcher.submit_task("test", {"x": 1})
        run = await dispatcher.get_run(run_id)
        
        assert run is not None
        assert run.spec.kind == "task"
        assert run.spec.name == "test"
        assert run.spec.params == {"x": 1}
        # MemoryExecutor runs synchronously, so status is completed
        assert run.status == RunStatus.COMPLETED
    
    @pytest.mark.asyncio
    async def test_convenience_wrappers_match_canonical(self):
        """Test that convenience wrappers create correct specs."""
        executor = StubExecutor()
        dispatcher = EventDispatcher(executor=executor)
        
        # Test each convenience wrapper
        task_id = await dispatcher.submit_task("t1", {"a": 1})
        pipe_id = await dispatcher.submit_pipeline("p1", {"b": 2})
        workflow_id = await dispatcher.submit_workflow("w1", {"c": 3})
        step_id = await dispatcher.submit_step("s1", {"d": 4}, parent_run_id=workflow_id)
        
        task_run = await dispatcher.get_run(task_id)
        pipe_run = await dispatcher.get_run(pipe_id)
        workflow_run = await dispatcher.get_run(workflow_id)
        step_run = await dispatcher.get_run(step_id)
        
        assert task_run.spec.kind == "task"
        assert pipe_run.spec.kind == "pipeline"
        assert workflow_run.spec.kind == "workflow"
        assert step_run.spec.kind == "step"
        assert step_run.spec.parent_run_id == workflow_id
    
    @pytest.mark.asyncio
    async def test_idempotency_key(self):
        """Test that idempotency key prevents duplicates."""
        executor = StubExecutor()
        dispatcher = EventDispatcher(executor=executor)
        
        # Submit with idempotency key
        run_id_1 = await dispatcher.submit_task(
            "test", {}, idempotency_key="unique-key-123"
        )
        
        # Submit again with same key
        run_id_2 = await dispatcher.submit_task(
            "test", {}, idempotency_key="unique-key-123"
        )
        
        # Should return same run
        assert run_id_1 == run_id_2
        
        # Different key creates new run
        run_id_3 = await dispatcher.submit_task(
            "test", {}, idempotency_key="different-key"
        )
        assert run_id_3 != run_id_1
    
    @pytest.mark.asyncio
    async def test_events_recorded(self):
        """Test that events are recorded during lifecycle."""
        executor = StubExecutor()
        dispatcher = EventDispatcher(executor=executor)
        
        run_id = await dispatcher.submit_task("test", {})
        events = await dispatcher.get_events(run_id)
        
        event_types = [e.event_type for e in events]
        assert EventType.CREATED in event_types
        assert EventType.QUEUED in event_types
    
    @pytest.mark.asyncio
    async def test_list_runs_with_filters(self):
        """Test list_runs filtering."""
        executor = StubExecutor()
        dispatcher = EventDispatcher(executor=executor)
        
        # Create various runs
        await dispatcher.submit_task("task1", {})
        await dispatcher.submit_task("task2", {})
        await dispatcher.submit_pipeline("pipe1", {})
        
        # Filter by kind
        tasks = await dispatcher.list_runs(kind="task")
        assert len(tasks) == 2
        
        pipes = await dispatcher.list_runs(kind="pipeline")
        assert len(pipes) == 1
        
        # Filter by name
        task1s = await dispatcher.list_runs(name="task1")
        assert len(task1s) == 1
    
    @pytest.mark.asyncio
    async def test_retry_creates_new_run(self):
        """Test that retry creates a linked run."""
        executor = StubExecutor()
        dispatcher = EventDispatcher(executor=executor)
        
        # Create and fail a run
        original_id = await dispatcher.submit_task("test", {"x": 1})
        original = await dispatcher.get_run(original_id)
        original.status = RunStatus.FAILED
        await dispatcher._save_run(original)
        
        # Retry
        retry_id = await dispatcher.retry(original_id)
        
        assert retry_id != original_id
        
        retry_run = await dispatcher.get_run(retry_id)
        assert retry_run.retry_of_run_id == original_id
        assert retry_run.attempt == 2
        assert retry_run.spec.trigger_source == "retry"
    
    @pytest.mark.asyncio
    async def test_get_children(self):
        """Test getting workflow children (steps)."""
        executor = StubExecutor()
        dispatcher = EventDispatcher(executor=executor)
        
        # Create workflow and steps
        workflow_id = await dispatcher.submit_workflow("my_workflow", {})
        await dispatcher.submit_step("step1", {}, parent_run_id=workflow_id)
        await dispatcher.submit_step("step2", {}, parent_run_id=workflow_id)
        
        # Get children
        children = await dispatcher.get_children(workflow_id)
        assert len(children) == 2


class TestEndToEndWithMemoryExecutor:
    """End-to-end tests with actual execution."""
    
    @pytest.mark.asyncio
    async def test_full_task_lifecycle(self):
        """Test complete task lifecycle with real execution."""
        registry = HandlerRegistry()
        
        @register_task("multiply", registry=registry)
        def multiply(params):
            return {"result": params["a"] * params["b"]}
        
        executor = MemoryExecutor(handlers=registry.to_executor_handlers())
        dispatcher = EventDispatcher(executor=executor, registry=registry)
        
        # Submit
        run_id = await dispatcher.submit_task("multiply", {"a": 6, "b": 7})
        
        # Query
        run = await dispatcher.get_run(run_id)
        # MemoryExecutor runs synchronously, so status should be completed
        assert run.status == RunStatus.COMPLETED
        assert run.result == {"result": 42}
        
        # Events
        events = await dispatcher.get_events(run_id)
        assert len(events) >= 3  # created, queued, completed
    
    @pytest.mark.asyncio
    async def test_registry_and_dispatcher_integration(self):
        """Test that registry integrates properly with EventDispatcher."""
        registry = HandlerRegistry()
        
        @register_task("greet", registry=registry, description="Says hello")
        def greet(params):
            return {"message": f"Hello, {params['name']}!"}
        
        @register_pipeline("process", registry=registry)
        def process(params):
            return {"processed": len(params.get("items", []))}
        
        executor = MemoryExecutor(handlers=registry.to_executor_handlers())
        dispatcher = EventDispatcher(executor=executor, registry=registry)
        
        # Both should work
        task_id = await dispatcher.submit_task("greet", {"name": "World"})
        pipe_id = await dispatcher.submit_pipeline("process", {"items": [1, 2, 3]})
        
        task_run = await dispatcher.get_run(task_id)
        pipe_run = await dispatcher.get_run(pipe_id)
        
        # MemoryExecutor runs synchronously, so status should be completed
        assert task_run.status == RunStatus.COMPLETED
        assert pipe_run.status == RunStatus.COMPLETED
        
        # Check results
        assert task_run.result == {"message": "Hello, World!"}
        assert pipe_run.result == {"processed": 3}
        
        # Check metadata
        metadata = registry.get_metadata("task", "greet")
        assert metadata["description"] == "Says hello"
