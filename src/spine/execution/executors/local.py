"""Local threadpool executor for development and small-scale production.

This executor uses Python's ThreadPoolExecutor for concurrent execution.
It's good for development and small-scale production when you don't want
the overhead of Celery.
"""
import asyncio
import uuid
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Dict, Callable, Any
from ..spec import WorkSpec


class LocalExecutor:
    """ThreadPoolExecutor-based executor.
    
    Good for:
    - Development
    - Small-scale production
    - When you don't want Celery overhead
    
    Features:
    - Async/non-blocking submission
    - Configurable worker count
    - Cancellation support (for pending work)
    
    Example:
        >>> def process_data(params):
        ...     return {"processed": len(params["data"])}
        >>>
        >>> executor = LocalExecutor(max_workers=4)
        >>> executor.register_handler("task", "process", process_data)
        >>> ref = await executor.submit(task_spec("process", {"data": [1,2,3]}))
    """
    
    def __init__(
        self,
        max_workers: int = 4,
        handlers: Dict[str, Callable] | None = None
    ):
        """Initialize with worker pool.
        
        Args:
            max_workers: ThreadPool size (default: 4)
            handlers: Map of "kind:name" -> handler function
        """
        self.pool = ThreadPoolExecutor(max_workers=max_workers)
        self.handlers = handlers or {}
        self._futures: Dict[str, Future] = {}
        self._results: Dict[str, Any] = {}
    
    def register_handler(self, kind: str, name: str, handler: Callable) -> None:
        """Register a handler at runtime.
        
        Args:
            kind: Work kind (task, pipeline, workflow, step)
            name: Handler name
            handler: Callable(params: dict) -> Any (sync only for ThreadPool)
        """
        key = f"{kind}:{name}"
        self.handlers[key] = handler
    
    async def submit(self, spec: WorkSpec) -> str:
        """Submit work to thread pool.
        
        Work is queued in the thread pool and a reference is returned
        immediately. Use get_status() to check progress.
        
        Raises:
            ValueError: If no handler registered for spec.kind:spec.name
        """
        external_ref = f"local-{uuid.uuid4().hex[:8]}"
        
        # Look up handler
        handler_key = f"{spec.kind}:{spec.name}"
        if handler_key not in self.handlers:
            raise ValueError(f"No handler for {handler_key}")
        
        handler = self.handlers[handler_key]
        
        # Create wrapper to capture result
        def run_and_capture():
            try:
                result = handler(spec.params)
                self._results[external_ref] = {"status": "completed", "result": result}
                return result
            except Exception as e:
                self._results[external_ref] = {"status": "failed", "error": str(e)}
                raise
        
        # Submit to thread pool
        future = self.pool.submit(run_and_capture)
        self._futures[external_ref] = future
        
        return external_ref
    
    async def cancel(self, external_ref: str) -> bool:
        """Cancel pending/running work.
        
        Note: Only pending (not yet started) work can be cancelled.
        Running work will continue to completion.
        """
        future = self._futures.get(external_ref)
        if not future:
            return False
        return future.cancel()
    
    async def get_status(self, external_ref: str) -> str | None:
        """Get status from future state."""
        future = self._futures.get(external_ref)
        if not future:
            return None
        
        if future.cancelled():
            return "cancelled"
        elif future.done():
            return "completed" if not future.exception() else "failed"
        elif future.running():
            return "running"
        else:
            return "queued"
    
    async def get_result(self, external_ref: str, timeout: float | None = None) -> Any:
        """Get result, optionally waiting for completion.
        
        Args:
            external_ref: Runtime identifier
            timeout: Max seconds to wait (None = don't wait)
            
        Returns:
            Result if completed, None otherwise
            
        Raises:
            TimeoutError: If timeout exceeded while waiting
        """
        future = self._futures.get(external_ref)
        if not future:
            return None
        
        if timeout is not None:
            # Wait for completion
            loop = asyncio.get_event_loop()
            try:
                await asyncio.wait_for(
                    loop.run_in_executor(None, future.result, timeout),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                raise TimeoutError(f"Waiting for {external_ref} exceeded {timeout}s")
        
        if future.done() and not future.exception():
            return future.result()
        return None
    
    def shutdown(self, wait: bool = True) -> None:
        """Shutdown thread pool.
        
        Args:
            wait: If True, wait for pending work to complete
        """
        self.pool.shutdown(wait=wait)
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.shutdown(wait=True)
