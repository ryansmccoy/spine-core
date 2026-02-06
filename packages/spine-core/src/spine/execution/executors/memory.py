"""In-memory executor for testing and development.

This executor runs work synchronously in the current process. It's perfect
for unit tests and development but should NOT be used in production.
"""
import asyncio
import inspect
import uuid
from typing import Dict, Any, Callable
from ..spec import WorkSpec


class MemoryExecutor:
    """In-memory executor - runs work synchronously in current process.
    
    Perfect for:
    - Unit tests
    - Development
    - Debugging
    
    NOT for production (blocking, no persistence, lost on crash).
    
    Example:
        >>> async def my_handler(params):
        ...     return {"result": params["value"] * 2}
        >>>
        >>> executor = MemoryExecutor(handlers={"task:double": my_handler})
        >>> ref = await executor.submit(task_spec("double", {"value": 21}))
        >>> status = await executor.get_status(ref)  # "completed"
    """
    
    def __init__(self, handlers: Dict[str, Callable] | None = None):
        """Initialize with optional handler map.
        
        Args:
            handlers: Map of "kind:name" -> handler function.
                      Handler receives (params: dict) and returns result.
        """
        self.handlers = handlers or {}
        self._runs: Dict[str, Dict[str, Any]] = {}  # external_ref -> run data
    
    def register_handler(self, kind: str, name: str, handler: Callable) -> None:
        """Register a handler at runtime.
        
        Args:
            kind: Work kind (task, pipeline, workflow, step)
            name: Handler name
            handler: Callable(params: dict) -> Any
        """
        key = f"{kind}:{name}"
        self.handlers[key] = handler
    
    async def submit(self, spec: WorkSpec) -> str:
        """Run work immediately in current process.
        
        The handler is looked up and executed synchronously (or awaited
        if it's an async function). Results are stored in memory.
        """
        external_ref = f"mem-{uuid.uuid4().hex[:8]}"
        
        # Look up handler
        handler_key = f"{spec.kind}:{spec.name}"
        if handler_key not in self.handlers:
            self._runs[external_ref] = {
                "status": "failed",
                "error": f"No handler for {handler_key}",
                "result": None,
            }
            return external_ref
        
        # Execute
        try:
            handler = self.handlers[handler_key]
            if inspect.iscoroutinefunction(handler):
                result = await handler(spec.params)
            else:
                result = handler(spec.params)
            
            self._runs[external_ref] = {
                "status": "completed",
                "result": result,
                "error": None,
            }
        except Exception as e:
            self._runs[external_ref] = {
                "status": "failed",
                "error": str(e),
                "result": None,
            }
        
        return external_ref
    
    async def cancel(self, external_ref: str) -> bool:
        """Not supported for synchronous execution.
        
        Always returns False since work completes immediately.
        """
        return False
    
    async def get_status(self, external_ref: str) -> str | None:
        """Get status from in-memory cache."""
        run_data = self._runs.get(external_ref)
        return run_data["status"] if run_data else None
    
    async def get_result(self, external_ref: str) -> Any:
        """Get result from in-memory cache (MemoryExecutor-specific)."""
        run_data = self._runs.get(external_ref)
        return run_data.get("result") if run_data else None
    
    async def get_error(self, external_ref: str) -> str | None:
        """Get error from in-memory cache (MemoryExecutor-specific)."""
        run_data = self._runs.get(external_ref)
        return run_data.get("error") if run_data else None
    
    def clear(self) -> None:
        """Clear all run data (for testing)."""
        self._runs.clear()
