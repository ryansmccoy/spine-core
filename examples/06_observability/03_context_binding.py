#!/usr/bin/env python3
"""Context Binding — Thread-local context for observability.

WHY CONTEXT BINDING
───────────────────
When a request flows through 10 functions, manually passing
request_id, batch_id, and domain to every log call is tedious and
error-prone.  Context binding sets these fields *once* and they
automatically appear in every subsequent log line until cleared.

CONTEXT FLOW
────────────
    add_context(request_id="req-123", domain="finra")
         │
         ▼
    log.info("step 1")  → {event: "step 1", request_id: "req-123"}
    log.info("step 2")  → {event: "step 2", request_id: "req-123"}
         │
    add_context(stage="transform")
         │
         ▼
    log.info("step 3")  → {event: ..., request_id: "req-123",
                            stage: "transform"}
         │
    clear_context()
         │
         ▼
    log.info("step 4")  → {event: "step 4"}   (context gone)

SCOPING PATTERNS
────────────────
    Pattern          Behaviour              When
    ──────────────── ────────────────────── ───────────────────
    Additive         add_context accumulates API request handlers
    Isolated         save/clear/restore     Sub-operations
    Per-request      clear at entry         HTTP middleware

BEST PRACTICES
──────────────
• Bind request_id, batch_id, domain at the entry point.
• Add stage context as the operation progresses.
• Always clear_context() when a request/batch completes.
• Use the isolation pattern for sub-operations that need
  their own context without polluting the parent.

Run: python examples/06_observability/03_context_binding.py

See Also:
    01_structured_logging — how context appears in log output
    02_metrics — correlate metrics with context fields
"""
from spine.observability import (
    get_logger,
    configure_logging,
    add_context,
    clear_context,
    get_context,
)
from spine.core import new_batch_id


def main():
    print("=" * 60)
    print("Context Binding Examples")
    print("=" * 60)
    
    # Configure logging
    configure_logging(level="INFO")
    log = get_logger("context_demo")
    
    # === 1. Basic context binding ===
    print("\n[1] Basic Context Binding")
    
    # Add context
    add_context(request_id="req-12345")
    log.info("Message with request_id context")
    
    # Get current context
    ctx = get_context()
    print(f"  Current context: {ctx}")
    
    # Clear context
    clear_context()
    log.info("Message after context cleared")
    
    # === 2. Multiple context fields ===
    print("\n[2] Multiple Context Fields")
    
    add_context(
        batch_id=new_batch_id(),
        domain="finra_otc",
        environment="production",
        user="system",
    )
    
    log.info("Processing started")
    log.info("Processing step 1")
    log.info("Processing step 2")
    
    ctx = get_context()
    print(f"  Context fields: {list(ctx.keys())}")
    
    clear_context()
    
    # === 3. Context in functions ===
    print("\n[3] Context in Functions")
    
    def process_batch(batch_id: str, records: list):
        """Process a batch with context."""
        add_context(batch_id=batch_id, record_count=len(records))
        
        log.info("Starting batch processing")
        
        for i, record in enumerate(records):
            log.debug("Processing record", record_index=i)
        
        log.info("Batch processing complete")
        
        # Context persists until cleared
    
    process_batch("batch-001", [1, 2, 3])
    log.info("After function (context still set)")
    
    clear_context()
    log.info("After clear")
    
    # === 4. Nested context scopes ===
    print("\n[4] Nested Context Scopes")
    
    def outer_function():
        add_context(layer="outer")
        log.info("In outer function")
        
        inner_function()
        
        log.info("Back in outer function")
    
    def inner_function():
        add_context(layer="inner")  # Adds to existing context
        log.info("In inner function")
    
    outer_function()
    clear_context()
    
    # === 5. Context for error tracking ===
    print("\n[5] Context for Error Tracking")
    
    def risky_operation(item_id: str):
        """Operation that might fail."""
        add_context(item_id=item_id, operation="risky")
        
        try:
            if item_id == "bad":
                raise ValueError("Invalid item")
            log.info("Operation succeeded")
        except Exception as e:
            log.error("Operation failed", error=str(e))
            raise
    
    risky_operation("good")
    clear_context()
    
    try:
        risky_operation("bad")
    except ValueError:
        pass
    clear_context()
    
    # === 6. Real-world: Request tracing ===
    print("\n[6] Real-world: Request Tracing")
    
    def handle_request(request_id: str, endpoint: str, user_id: str):
        """Handle an API request with full tracing context."""
        # Set up request context
        add_context(
            request_id=request_id,
            endpoint=endpoint,
            user_id=user_id,
        )
        
        log.info("Request received")
        
        # Simulate processing stages
        validate_request()
        process_request()
        send_response()
        
        log.info("Request completed")
    
    def validate_request():
        add_context(stage="validation")
        log.info("Validating request")
    
    def process_request():
        add_context(stage="processing")
        log.info("Processing request")
    
    def send_response():
        add_context(stage="response")
        log.info("Sending response")
    
    handle_request(
        request_id="req-abc123",
        endpoint="/api/v1/data",
        user_id="user-456",
    )
    clear_context()
    
    # === 7. Context isolation pattern ===
    print("\n[7] Context Isolation Pattern")
    
    def isolated_operation(name: str):
        """Operation with isolated context."""
        # Save current context
        saved_context = get_context().copy()
        
        try:
            # Clear and set new context
            clear_context()
            add_context(operation=name)
            
            log.info(f"Running {name}")
            
        finally:
            # Restore previous context
            clear_context()
            for key, value in saved_context.items():
                add_context(**{key: value})
    
    add_context(global_field="preserved")
    isolated_operation("isolated_task")
    
    ctx = get_context()
    print(f"  Context after isolation: {ctx}")
    
    clear_context()
    
    print("\n" + "=" * 60)
    print("[OK] Context Binding Complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
