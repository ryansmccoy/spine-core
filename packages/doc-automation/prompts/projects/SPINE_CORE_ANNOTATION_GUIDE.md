# 🏗️ Spine-Core - Annotation Guide

**Project-Specific Guide for Annotating Spine-Core Classes**

*For use with Documentation Automation Package - February 2026*

---

## 📋 PROJECT CONTEXT

### What is Spine-Core?

**Spine-Core** is a registry-driven data pipeline framework for financial market data:

> *"I need a framework where domains (EntitySpine, FeedSpine, Market-Spine) can extend without modifying core primitives"*

### Core Philosophy

**Principle #1: Registry-Driven Architecture**

Pipelines discover sources and schemas automatically:
- **No hardcoded imports** - Use registry to discover adapters
- **Runtime configuration** - Add new sources without code changes
- **Domain isolation** - Domains extend framework, don't modify it

**Principle #2: Capture Semantics**

All data is append-only with revision tracking:
- **Never delete** - Mark as inactive/archived
- **Never update in place** - Create new version
- **Always track provenance** - Who, when, why, source

Enables full audit trail and time travel.

**Principle #3: Quality Gates**

Built-in validation and anomaly detection:
- **Schema validation** - Pydantic models
- **Business rules** - Domain-specific constraints
- **Anomaly detection** - Statistical outliers, missing data
- **Quality scores** - Confidence levels

**Principle #4: Domain Isolation**

Domains (EntitySpine, FeedSpine, Market-Spine) are independent:
- **Shared primitives** - Result[T], ExecutionContext, Registry
- **Domain packages** - Each domain is separate Python package
- **Minimal coupling** - Domains communicate via well-defined interfaces

### Key Concepts

1. **Registry** - Central catalog of sources, schemas, adapters
2. **Dispatcher** - Route data to appropriate processors
3. **Capture** - Append-only data capture with revisions
4. **Quality Gate** - Validation, anomaly detection, scoring
5. **Domain** - Isolated package (EntitySpine, FeedSpine, etc.)
6. **Base Classes** - Abstract classes for adapters, processors, stores

### Architecture Patterns

1. **Registry Pattern** - Discover components at runtime
2. **Dispatcher Pattern** - Route data to handlers
3. **Template Method** - Base classes with hooks for customization
4. **Strategy Pattern** - Pluggable storage/processing backends

---

## 🎯 CLASSES TO ANNOTATE

### ⚠️ IMPORTANT: Shared Primitives Location

The core primitives (`Result[T]`, `Ok`, `Err`, `ExecutionContext`) are **currently defined in EntitySpine**:

```
entityspine/src/entityspine/domain/workflow.py:
  - Ok[T] - Success variant
  - Err - Error variant  
  - ExecutionContext - Tracing context
  - ErrorCategory - Error classification enum
```

**Future State**: These will be factored out into `spine-core` as the single source of truth. All domain packages will import from spine-core.

**For now**: When annotating these classes in EntitySpine, note they are "shared across all Spine projects" and will move to spine-core.

---

### **Tier 1 (MUST Annotate - When Classes Exist)**

#### Core Primitives (Currently in EntitySpine - Will Move Here)

| Class | Current Location | Priority | Why |
|-------|------------------|----------|-----|
| `Ok[T]` | `entityspine/domain/workflow.py` | **10** | Success variant - used EVERYWHERE |
| `Err` | `entityspine/domain/workflow.py` | **10** | Error variant - used EVERYWHERE |
| `ExecutionContext` | `entityspine/domain/workflow.py` | **10** | Tracing context |
| `ErrorCategory` | `entityspine/domain/errors.py` | 9 | Error classification |

#### Registry/Dispatcher (To Be Created)

| Class | File | Priority | Why |
|-------|------|----------|-----|
| `Registry` | `registry.py` | **10** | Component registration/discovery |
| `Dispatcher` | `dispatcher.py` | **10** | Route data to processors |

#### Base Classes (To Be Created)

| Class | File | Priority | Why |
|-------|------|----------|-----|
| `BaseAdapter` | `base/adapter.py` | 9 | Template for all domain adapters |
| `BaseProcessor` | `base/processor.py` | 9 | Template for transformation logic |
| `BaseStore` | `base/store.py` | 9 | Template for storage implementations |

#### Quality Gates (To Be Created)

| Class | File | Priority | Why |
|-------|------|----------|-----|
| `Validator` | `quality/validator.py` | 9 | Schema validation |
| `AnomalyDetector` | `quality/anomaly.py` | 8 | Statistical outlier detection |
| `QualityScorer` | `quality/scorer.py` | 8 | Confidence scoring |

---

### **Tier 2 (SHOULD Annotate)**

- **Configuration models**: `RegistryConfig`, `DispatcherConfig`
- **Protocol definitions**: `AdapterProtocol`, `StoreProtocol`, `ProcessorProtocol`
- **Error classes**: `RegistryError`, `DispatcherError`
- **Metrics collectors**: `PipelineMetrics`, `QualityMetrics`

---

## 📝 PROJECT-SPECIFIC ANNOTATION GUIDELINES

### Result[T] Pattern - Shared Across ALL Projects

The `Result[T]` pattern (Ok/Err) is used across ALL Spine projects:

```python
# Current location (will move to spine-core)
from entityspine.domain.workflow import Ok, Err, Result

# When annotating in EntitySpine, note:
"""
    Note:
        This class is SHARED across all Spine projects:
        - EntitySpine: Entity resolution results
        - FeedSpine: Feed fetch results
        - GenAI-Spine: LLM responses  
        - Capture-Spine: Content capture results
        - Market-Spine: Market data queries
        
        Future: Will be factored out to spine-core as the
        canonical source of truth.
"""
```

### Manifesto Section - Framework Principles
   - Why: Template for transformation logic
   - Tags: `base_class`, `processor`, `transformation`

7. **`BaseStore`** - Abstract storage backend
   - Priority: 9
   - Why: Template for storage implementations
   - Tags: `base_class`, `storage`, `persistence`

#### Quality Gates
8. **`Validator`** - Schema validation
9. **`AnomalyDetector`** - Statistical outlier detection
10. **`QualityScorer`** - Confidence scoring

---

### **Tier 2 (SHOULD Annotate)**

11. **Configuration models** (RegistryConfig, DispatcherConfig)
12. **Protocol definitions** (AdapterProtocol, StoreProtocol)
13. **Error classes** (RegistryError, DispatcherError)
14. **Metrics collectors** (PipelineMetrics, QualityMetrics)

---

## 📝 PROJECT-SPECIFIC ANNOTATION GUIDELINES

### Manifesto Section - Framework Principles

```python
Manifesto:
    Registry-driven architecture eliminates hardcoded dependencies:
    
    [For Registry]
    Domains register adapters, schemas, processors at startup.
    Framework discovers them at runtime via registry lookup.
    Add new source? Register it. No code changes.
    
    [For Capture]
    Append-only semantics ensure full audit trail:
    - Never delete (mark inactive)
    - Never update in place (create new version)
    - Always track provenance (who, when, source)
    
    Enables time travel: "What was the value at 2pm yesterday?"
    
    [For Quality Gates]
    Built-in validation prevents garbage-in-garbage-out:
    - Schema validation (types, constraints)
    - Business rules (domain-specific logic)
    - Anomaly detection (statistical outliers)
    - Quality scoring (confidence levels)
    
    [For Domain Isolation]
    Domains are independent Python packages:
    - entityspine: Master data (entities, identifiers)
    - feedspine: Feed capture (RSS, APIs)
    - market-spine: Market data (prices, quotes)
    
    Shared primitives (Result[T], ExecutionContext) ensure
    consistency across domains.
```

### Architecture Section - Framework Design

```python
Architecture:
    ```
    Startup Phase:
    ┌─────────────────────────┐
    │  Domain Packages:       │
    │  entityspine/           │
    │  feedspine/             │
    │  market-spine/          │
    └───────────┬─────────────┘
                ↓
    Register Components:
    - Adapters (RSS, JSON, SQL)
    - Schemas (Entity, Feed, Price)
    - Processors (Validate, Transform)
    - Stores (SQLite, PostgreSQL)
                ↓
    ┌─────────────────────────┐
    │  Registry               │
    │  (Component Catalog)    │
    └─────────────────────────┘
    
    Runtime Phase:
    Data → Dispatcher
         ↓
    Registry Lookup (which adapter?)
         ↓
    Adapter.fetch()
         ↓
    Quality Gate (validate, detect anomalies)
         ↓
    Processor.transform()
         ↓
    Store.persist()
    ```
    
    Registration: Startup (decorator pattern)
    Discovery: Runtime (registry lookup)
    Validation: Quality gates (Pydantic + custom rules)
    Capture: Append-only (audit trail, time travel)
```

### Tags - Spine-Core Specific

- **Core Primitives**: `core_primitive`, `result_type`, `execution_context`, `error_handling`
- **Architecture**: `registry`, `dispatcher`, `discovery`, `routing`
- **Base Classes**: `base_class`, `template_method`, `adapter_pattern`, `abstract`
- **Quality**: `validation`, `anomaly_detection`, `quality_scoring`, `data_quality`
- **Capture**: `append_only`, `audit_trail`, `time_travel`, `provenance`
- **Framework**: `framework`, `extensibility`, `domain_isolation`

### Doc-Types

```python
Doc-Types:
    - MANIFESTO (section: "Framework Principles", priority: 10)
      # Registry-driven, capture semantics, quality gates
    
    - ARCHITECTURE (section: "Framework Design", priority: 10)
      # Registry, dispatcher, domain isolation
    
    - CORE_PRIMITIVES (section: "Shared Types", priority: 10)
      # Result[T], ExecutionContext, ErrorCategory
    
    - UNIFIED_DATA_MODEL (section: "Framework Abstractions", priority: 9)
      # Base classes, protocols, interfaces
    
    - GUARDRAILS (section: "Framework Usage", priority: 9)
      # How to extend framework correctly
```

### Framework Extension Annotations

For base classes and protocols:

```python
Framework-Extension:
    How to Extend:
    ```python
    from spine_core import BaseAdapter, Registry
    
    class MyCustomAdapter(BaseAdapter):
        """Adapt data from custom source."""
        
        def fetch(self, config: dict) -> Result[list[dict]]:
            # Implementation
            pass
    
    # Register at startup
    @Registry.register("adapters", "my_custom")
    def create_adapter():
        return MyCustomAdapter()
    ```
    
    Best Practices:
    - Always use Result[T] for error handling
    - Always accept ExecutionContext for tracing
    - Always validate inputs (Pydantic models)
    - Never modify base class behavior
    - Use registry for discovery, not imports
    
    See: guides/EXTENDING_FRAMEWORK.md
```

---

## 📚 REFERENCE DOCUMENTS

1. **Spine-Core README**: `spine-core/README.md`
   - Registry architecture, capture semantics

2. **Framework Design Docs**: `spine-core/docs/` (when created)
   - Registry pattern, dispatcher, quality gates

3. **EntitySpine Core Types**: `entityspine/src/entityspine/domain/core.py`
   - Result[T], ExecutionContext reference implementation

---

## 📖 EXAMPLE ANNOTATED CLASS

```python
from typing import TypeVar, Generic
from dataclasses import dataclass

T = TypeVar('T')
E = TypeVar('E')

class Result(Generic[T, E]):
    """
    Success/failure monad for error handling.
    
    Used across ALL Spine projects for consistent error handling.
    Replaces try/except with explicit Ok/Err types.
    
    Manifesto:
        Result[T] eliminates hidden exceptions and forces explicit
        error handling.
        
        Instead of:
        ```python
        try:
            value = fetch_data()  # Might raise exception
        except Exception as e:
            # Handle error
        ```
        
        Use:
        ```python
        result: Result[Data] = fetch_data()
        match result:
            case Ok(data):
                # Success case
            case Err(error):
                # Error case
        ```
        
        Benefits:
        - Type-safe error handling (mypy/pyright)
        - Explicit error cases (no hidden exceptions)
        - Composable (map, flatmap, unwrap_or)
        - Consistent across all Spine projects
        
        Shared across:
        - EntitySpine: Entity resolution results
        - FeedSpine: Feed fetch results
        - GenAI-Spine: LLM responses
        - Capture-Spine: Content capture results
        - Market-Spine: Market data queries
    
    Architecture:
        ```
        Result[T, E]:
        - Ok(value: T): Success case
        - Err(error: E): Failure case
        
        Pattern matching (Python 3.10+):
        match result:
            case Ok(value): ...
            case Err(error): ...
        
        Composition:
        result.map(transform)      # Transform success value
        result.flatmap(chain)       # Chain operations
        result.unwrap_or(default)   # Extract or default
        result.unwrap()             # Extract or raise
        ```
        
        Implementation: Algebraic data type (sum type)
        Type Safety: Full mypy/pyright support
        Composition: Monadic interface (map, flatmap)
    
    Examples:
        >>> from spine_core import Result, Ok, Err
        >>> 
        >>> # Success case
        >>> result: Result[int] = Ok(42)
        >>> match result:
        ...     case Ok(value):
        ...         print(f"Got {value}")
        ...     case Err(error):
        ...         print(f"Error: {error}")
        Got 42
        
        # Failure case
        >>> result: Result[int] = Err("Division by zero")
        >>> value = result.unwrap_or(0)  # Returns 0
        0
        
        # Composition
        >>> Ok(5).map(lambda x: x * 2).unwrap()
        10
        
        # Real usage in EntitySpine
        >>> from entityspine import EntityResolver
        >>> 
        >>> resolver = EntityResolver()
        >>> result: Result[Entity] = resolver.resolve("AAPL")
        >>> match result:
        ...     case Ok(entity):
        ...         print(f"Resolved: {entity.name}")
        ...     case Err(error):
        ...         print(f"Failed: {error}")
    
    Tags:
        - core_primitive
        - result_type
        - error_handling
        - monad
        - type_safety
        - shared_across_domains
    
    Doc-Types:
        - MANIFESTO (section: "Error Handling", priority: 10)
        - CORE_PRIMITIVES (section: "Result Type", priority: 10)
        - UNIFIED_DATA_MODEL (section: "Shared Types", priority: 10)
        - API_REFERENCE (section: "Core Types", priority: 10)
    """
    ...
```

---

## ✅ VALIDATION CHECKLIST

### Framework-Specific
- [ ] Mentions registry-driven architecture
- [ ] Explains capture semantics (append-only)
- [ ] Notes domain isolation
- [ ] Includes extension guide (how to extend)
- [ ] References shared primitives (Result[T], ExecutionContext)

### Quality
- [ ] At least 3 tags
- [ ] At least 2 doc-types
- [ ] Examples show framework usage
- [ ] No TODO or placeholder text

---

## 🚀 QUICK START

1. **Read this guide** (5 minutes)
2. **Read Registry/Dispatcher design docs** (when available)
3. **Read EXTENDED_ANNOTATION_PROMPT.md** (15 minutes)
4. **Annotate shared primitives first** (Result[T], ExecutionContext)
5. **Then annotate base classes** (BaseAdapter, BaseStore)
6. **Focus on framework extension patterns**

---

**Note**: Spine-Core is the foundation. Get these annotations right - they set the pattern for ALL domain packages!
