# 🚀 IMPLEMENTATION MEGA PROMPT

## Autonomous Class Annotation for Spine Ecosystem

**Use this prompt to have an LLM annotate all classes across the Spine ecosystem according to the project-specific guides.**

---

## 📋 TASK OVERVIEW

You are a documentation automation agent. Your task is to **add extended docstrings** to Python classes in the Spine ecosystem. Each class should be annotated with rich documentation that will later be extracted to generate architecture docs, feature guides, and API references.

### What You Will Do

1. Read the project-specific annotation guide
2. Identify classes to annotate (Tier 1 first, then Tier 2)
3. Read each class's source code
4. Write an extended docstring following the format
5. Edit the file to add the docstring
6. Validate against the checklist
7. Move to the next class

---

## 🎯 THE PROMPT

Copy everything below this line and send to an LLM with access to file editing tools:

---

# ANNOTATION TASK: [PROJECT_NAME]

## Your Role

You are a documentation automation agent for the **[PROJECT_NAME]** project in the Spine ecosystem. Your task is to add extended docstrings to Python classes following a specific format that enables automatic documentation generation.

## Reference Guide

Read this guide first - it contains everything you need:
**`spine-core/packages/doc-automation/prompts/projects/[PROJECT]_ANNOTATION_GUIDE.md`**

The guide provides:
- Project philosophy and principles
- Prioritized class lists (Tier 1, Tier 2, Tier 3)
- Project-specific annotation guidelines
- Example annotated classes
- Validation checklist

## Extended Docstring Format

Every annotated class should have a docstring with these sections:

```python
class ClassName:
    """
    One-line summary (what this class does).
    
    Extended description (2-3 sentences explaining purpose and context).
    
    Manifesto:
        Why this class exists and what principles it embodies.
        Reference project philosophy from the guide.
        Explain design decisions.
    
    Architecture:
        ```
        ASCII diagram showing data flow or structure
        ```
        
        Key architectural notes:
        - Dependencies
        - Storage tier (if applicable)
        - Concurrency model
        - Integration points
    
    Features:
        - Feature 1 description
        - Feature 2 description
        - Feature 3 description
    
    Examples:
        >>> # Doctest-format examples
        >>> instance = ClassName(param="value")
        >>> instance.method()
        'expected_output'
        
        # Real-world usage
        >>> from module import ClassName
        >>> result = ClassName.from_data(data)
    
    Performance:
        - Operation 1: O(n), ~Xms typical
        - Memory: ~X bytes per instance
        - Caching: LRU with TTL
    
    Guardrails:
        - Do NOT do X
          ✅ Instead: Do Y
        
        - Do NOT assume Z
          ✅ Instead: Check W first
        
        - ALWAYS do A before B
    
    Context:
        Problem: What problem does this solve?
        Solution: How does this class solve it?
        Alternatives Considered: What else was tried?
        Why This Approach: Rationale for current design.
    
    ADR:
        - 001-relevant-adr.md: Brief description
        - 003-another-adr.md: Why it applies
    
    Changelog:
        - v0.1.0: Initial implementation
        - v0.2.0: Added feature X
        - v0.3.0: Breaking change Y
    
    Tags:
        - tag1
        - tag2
        - tag3
    
    Doc-Types:
        - MANIFESTO (section: "Section Name", priority: 10)
        - FEATURES (section: "Section Name", priority: 9)
        - ARCHITECTURE (section: "Section Name", priority: 8)
    """
```

## Your Workflow

### Step 1: Read the Guide
```
Read: spine-core/packages/doc-automation/prompts/projects/[PROJECT]_ANNOTATION_GUIDE.md
```

Extract:
- Project philosophy (for Manifesto sections)
- Tier 1 class list with file paths
- Project-specific tags and doc-types
- Example annotated class

### Step 2: Process Tier 1 Classes

For each Tier 1 class:

1. **Read the source file**
   ```
   Read: [project]/src/[project]/[path]/[file].py
   ```

2. **Understand the class**
   - What does it do?
   - How does it relate to project principles?
   - What are common usage patterns?
   - What are the gotchas?

3. **Write the docstring**
   - Start with one-line summary
   - Add extended description
   - Fill in ALL sections from the format
   - Use project-specific principles from guide
   - Include real code examples

4. **Edit the file**
   - Replace existing docstring (if any) with extended version
   - Or add new docstring after class definition line

5. **Validate**
   - Check against guide's validation checklist
   - Ensure all required sections present
   - Verify examples are syntactically correct

### Step 3: Process Tier 2 Classes

Same workflow but:
- Can skip Context and ADR sections if not applicable
- Focus on Manifesto, Architecture, Features, Examples, Guardrails
- Still include Tags and Doc-Types

### Step 4: Summary Report

After completing all classes, report:
- Classes annotated (count)
- Any classes skipped (with reason)
- Any issues encountered

---

## 🎯 PROJECT-SPECIFIC PROMPTS

### EntitySpine Annotation Prompt

```
# ANNOTATION TASK: EntitySpine

You are annotating classes in the EntitySpine project - a zero-dependency entity resolution system for SEC EDGAR data.

## Key Principles to Emphasize

1. **Entity ≠ Security ≠ Listing** - This is THE foundational principle
2. **Claims-based identity** - Identifiers are claims, not facts
3. **Result[T] pattern** - Ok/Err for error handling, no exceptions
4. **Stdlib-only domain** - Zero dependencies in domain layer
5. **Tiered storage** - T0 (JSON) → T3 (PostgreSQL)

## Classes to Annotate (Tier 1)

1. `domain/workflow.py` → `Ok`, `Err`, `ExecutionContext`
2. `domain/entity.py` → `Entity`
3. `domain/security.py` → `Security`
4. `domain/listing.py` → `Listing`
5. `domain/claim.py` → `IdentifierClaim`
6. `domain/graph.py` → `Relationship`
7. `domain/observation.py` → `Observation`
8. `services/resolver.py` → `EntityResolver`
9. `services/graph_service.py` → `GraphService`
10. `services/fuzzy.py` → `FuzzyMatcher`
11. `stores/json/json_store.py` → `JsonEntityStore`
12. `stores/sqlite/storage.py` → `SqliteStore`

## Reference Guide
Read: spine-core/packages/doc-automation/prompts/projects/ENTITYSPINE_ANNOTATION_GUIDE.md

## Start
Begin with `Ok` and `Err` classes in `domain/workflow.py` - they are used everywhere.
```

---

### FeedSpine Annotation Prompt

```
# ANNOTATION TASK: FeedSpine

You are annotating classes in the FeedSpine project - a storage-agnostic feed capture framework.

## Key Principles to Emphasize

1. **Medallion Architecture** - Bronze (raw) → Silver (clean) → Gold (curated)
2. **Data Archetypes** - Observations, Events, Entities, Documents, Prices
3. **Storage-agnostic** - Swap backends without changing code
4. **Natural key deduplication** - Same content = one record, multiple sightings
5. **Composition operators** - Fluent pipeline API

## Classes to Annotate (Tier 1)

1. `pipeline.py` → `Pipeline`, `ProcessResult`, `PipelineStats`
2. `core/feedspine.py` → `FeedSpine`, `CollectionResult`
3. `adapter/base.py` → `FeedAdapter`, `BaseFeedAdapter`
4. `adapter/rss.py` → `RSSFeedAdapter`
5. `adapter/json.py` → `JSONFeedAdapter`
6. `adapter/file.py` → `FileFeedAdapter`
7. `protocols/storage.py` → `StorageBackend`
8. `storage/memory.py` → `MemoryStorage`
9. `storage/sqlite.py` → `SQLiteStorage`
10. `storage/duckdb.py` → `DuckDBStorage`
11. `storage/postgres.py` → `PostgresStorage`

## Reference Guide
Read: spine-core/packages/doc-automation/prompts/projects/FEEDSPINE_ANNOTATION_GUIDE.md

## Start
Begin with `FeedAdapter` protocol in `adapter/base.py` - it's the core abstraction.
```

---

### GenAI-Spine Annotation Prompt

```
# ANNOTATION TASK: GenAI-Spine

You are annotating classes in the GenAI-Spine project - a provider-agnostic LLM service.

## Key Principles to Emphasize

1. **Provider-agnostic** - Swap Ollama/OpenAI/Anthropic via config
2. **OpenAI-compatible API** - Drop-in replacement
3. **Cost tracking built-in** - Every call logged with tokens/cost
4. **Prompt management** - First-class versioned templates
5. **Ecosystem integration** - Uses EntitySpine's Result[T]

## Classes to Annotate (Tier 1) - PROVIDERS ARE CRITICAL!

1. `providers/base.py` → `LLMProvider` (ABC)
2. `providers/ollama.py` → `OllamaProvider`
3. `providers/openai.py` → `OpenAIProvider`
4. `providers/anthropic.py` → `AnthropicProvider`
5. `providers/registry.py` → `ProviderRegistry`
6. `settings.py` → `Settings`
7. `api/routers/chat.py` → `ChatCompletionRequest`, `ChatCompletionResponse`
8. `api/routers/capabilities.py` → `SummarizeRequest/Response`, `ExtractRequest/Response`
9. `api/routers/prompts.py` → `PromptCreateRequest`, `PromptResponse`
10. `api/routers/usage.py` → `UsageResponse`

## Reference Guide
Read: spine-core/packages/doc-automation/prompts/projects/GENAI_SPINE_ANNOTATION_GUIDE.md

## Start
Begin with `LLMProvider` in `providers/base.py` - it's THE core abstraction that enables provider-agnostic design.
```

---

### Capture-Spine Annotation Prompt

```
# ANNOTATION TASK: Capture-Spine

You are annotating classes in the Capture-Spine project - a point-in-time content capture system.

## Key Principles to Emphasize

1. **Point-in-time accuracy** - "What was visible at 2:30pm yesterday?"
2. **Feed → Item → Record → Sighting** - Data model hierarchy
3. **Content deduplication** - One record, multiple sightings
4. **Container DI** - Dependency injection for testability
5. **Modular architecture** - Domains + Features layers

## Classes to Annotate (Tier 1)

1. `app/container.py` → `Container`
2. `app/settings.py` → `Settings`, `DeploymentTier`
3. `app/models.py` → `FeedBase`, `FeedRead`, `ItemCreate`, `ItemRead`, `RecordCreate`, `RecordRead`, `SightingCreate`, `SightingRead`, `RunMetadata`, `SystemStatus`
4. Services: `SearchService`, `PollerService`, `ParserService`, `WorkSessionService`, `ChatSessionService`

## Reference Guide
Read: spine-core/packages/doc-automation/prompts/projects/CAPTURE_SPINE_ANNOTATION_GUIDE.md

## Start
Begin with `Container` in `app/container.py` - it wires everything together.
```

---

## 📊 BATCH EXECUTION STRATEGY

### Option 1: Sequential (Safest)
Annotate one project at a time, validate, then move to next.

```
1. EntitySpine (15 Tier 1 classes)
2. FeedSpine (15 Tier 1 classes)
3. GenAI-Spine (15 Tier 1 classes)
4. Capture-Spine (15 Tier 1 classes)
5. Review and iterate
```

### Option 2: Parallel by Tier
Annotate all Tier 1 classes across projects, then Tier 2.

```
Phase 1: All Tier 1 classes (~60 classes)
Phase 2: All Tier 2 classes (~120 classes)
Phase 3: Review and fill gaps
```

### Option 3: Critical Path First
Annotate shared primitives first, then project-specific.

```
Phase 1: Core Primitives
  - Ok, Err, ExecutionContext (EntitySpine - shared)
  - Result[T] pattern documentation

Phase 2: Core Abstractions
  - Entity, Security, Listing (EntitySpine)
  - FeedAdapter, Pipeline (FeedSpine)
  - LLMProvider hierarchy (GenAI-Spine)
  - Container (Capture-Spine)

Phase 3: Services
  - EntityResolver, GraphService
  - Storage backends
  - API models
```

---

## ✅ QUALITY GATES

### Per-Class Checklist
- [ ] One-line summary is clear and accurate
- [ ] Manifesto references project principles
- [ ] Architecture includes diagram (ASCII)
- [ ] Features list is complete
- [ ] Examples use doctest format (`>>>`)
- [ ] Examples are syntactically correct
- [ ] Guardrails warn about common mistakes
- [ ] At least 4 tags
- [ ] At least 2 doc-types
- [ ] No TODO or placeholder text

### Per-Project Checklist
- [ ] All Tier 1 classes annotated
- [ ] Validation checklist from guide passed
- [ ] Cross-references to related classes added
- [ ] Project principles consistently applied

---

## 🔧 TROUBLESHOOTING

### "I can't find the file"
Check the project structure. Common paths:
- EntitySpine: `entityspine/src/entityspine/`
- FeedSpine: `feedspine/src/feedspine/`
- GenAI-Spine: `genai-spine/src/genai_spine/`
- Capture-Spine: `capture-spine/app/`

### "The class doesn't exist"
The guide may reference planned classes. Skip and note in summary.

### "The class already has a docstring"
Replace it with the extended format, preserving any useful content.

### "I don't understand the class"
Read related classes, tests, and any existing documentation. Check imports to understand dependencies.

---

## 🎬 EXAMPLE SESSION

Here's how a session might look:

```
User: Annotate EntitySpine Tier 1 classes

Agent: I'll start by reading the EntitySpine annotation guide...

[Reads ENTITYSPINE_ANNOTATION_GUIDE.md]

Got it. Starting with Ok and Err classes in domain/workflow.py.

[Reads domain/workflow.py]

I see Ok and Err are frozen dataclasses implementing the Result[T] pattern. Let me write the extended docstring...

[Edits domain/workflow.py to add docstring to Ok class]

✅ Ok class annotated. Moving to Err class...

[Edits domain/workflow.py to add docstring to Err class]

✅ Err class annotated. Moving to ExecutionContext...

[Continues through all Tier 1 classes]

## Summary
- Annotated: 15 classes
- Skipped: 0
- Issues: None

Ready for Tier 2?
```

---

## 🚀 START HERE

1. **Choose a project** (recommend starting with EntitySpine)
2. **Copy the project-specific prompt** from above
3. **Send to LLM** with file editing capabilities
4. **Monitor progress** and provide guidance if needed
5. **Validate output** against checklists
6. **Repeat** for next project

---

**Good luck! The guides are turnkey - trust them and execute systematically.**
