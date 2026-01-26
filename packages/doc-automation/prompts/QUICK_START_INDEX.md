# 🚀 Implementation Prompts - Quick Start

## How to Use These Prompts

You have two options for implementing the annotation guides:

### Option 1: Quick Start Prompts (Recommended)

Copy-paste prompts ready for immediate use. **Each prompt is organized by feature importance and project evolution**, not file size.

| Project | Prompt | Phases | Files | Core Problem |
|---------|--------|--------|-------|--------------|
| **py-sec-edgar** | [QUICK_START_PY_SEC_EDGAR.md](QUICK_START_PY_SEC_EDGAR.md) | 7 | 32 | SEC EDGAR filing access |
| **Spine-Core** | [QUICK_START_SPINE_CORE.md](QUICK_START_SPINE_CORE.md) | 7 | 43 | Shared framework primitives |
| EntitySpine | [QUICK_START_ENTITYSPINE.md](QUICK_START_ENTITYSPINE.md) | 7 | 36 | CIK ↔ Ticker resolution |
| FeedSpine | [QUICK_START_FEEDSPINE.md](QUICK_START_FEEDSPINE.md) | 7 | 39 | Feed → Pipeline → Storage |
| GenAI-Spine | [QUICK_START_GENAI_SPINE.md](QUICK_START_GENAI_SPINE.md) | 5 | 31 | Provider-agnostic LLM |
| Capture-Spine | [QUICK_START_CAPTURE_SPINE.md](QUICK_START_CAPTURE_SPINE.md) | 6 | 29 | Point-in-time snapshots |

**Selection Methodology:**
- Phase 1 always solves the **original problem** the project was created for
- Later phases follow the **git history** (features added over time)
- Files grouped by **feature**, not alphabetically or by size

**Usage:**
1. Open the QUICK_START file for your project
2. Copy everything below the horizontal line
3. Paste into a new chat with Claude/GPT with file editing access
4. Work through phases in order (Phase 1 → 2 → 3...)

### Option 2: Mega Prompt (Advanced)

For batch execution across all projects:
- [IMPLEMENTATION_MEGA_PROMPT.md](IMPLEMENTATION_MEGA_PROMPT.md)

Contains:
- Full workflow instructions
- All project-specific prompts
- Batch execution strategies
- Quality gates
- Troubleshooting guide

---

## Recommended Order

```
0. py-sec-edgar (THE ORIGIN - started 2018, SEC EDGAR access)
   Phase 1: SEC client, downloads → HOW TO GET FILINGS
   Phase 4: Exhibits → THE HIDDEN VALUE (subsidiaries, contracts)

1. Spine-Core (do early - shared primitives used by all)
   Phase 1: Result[T], Errors → THE FOUNDATION
   Phase 5: Orchestration → WORKFLOW DAGs
   
2. EntitySpine (the original Spine project, CIK↔ticker)
   Phase 1: SEC data source, Lookup, Resolver → THE CORE PROBLEM
   Phase 2: Entity, Security, Listing → THE DATA MODEL
   
3. FeedSpine (uses EntitySpine patterns)
   Phase 1: Pipeline → THE COMPOSABLE ABSTRACTION
   Phase 2: Adapters → HOW DATA ENTERS
   
4. GenAI-Spine (uses Spine-Core's Result[T])
   Phase 1: Providers → THE SWAP-ABILITY
   Phase 2: Capabilities → WHAT LLMs DO
   
5. Capture-Spine (integrates all projects)
   Phase 1: Data Model → POINT-IN-TIME
   Phase 2: Features → EVERYTHING ELSE
```

---

## What Gets Created

After running the prompts, each class will have an extended docstring with:

- **Manifesto** - Why the class exists, project principles
- **Architecture** - ASCII diagrams, dependencies, data flow
- **Features** - What the class can do
- **Examples** - Runnable doctest examples
- **Performance** - Big-O, timing, memory
- **Guardrails** - Common mistakes and how to avoid them
- **Tags** - For documentation extraction
- **Doc-Types** - Where this appears in generated docs

---

## Full Documentation

- [Project-Specific Guides](projects/README.md) - Deep reference for each project
- [Extended Annotation Format](EXTENDED_ANNOTATION_PROMPT.md) - Full format specification
- [Validation Prompt](VALIDATION_PROMPT.md) - Check annotation quality
