# LLM Decision Prompt: Self-Documenting Code Strategy

## Context

You are a software architecture consultant evaluating 5 different approaches for building a self-documenting code system for a Python financial data library (EntitySpine/FeedSpine). The system should auto-generate documentation (MANIFESTO.md, FEATURES.md, architecture diagrams) from code annotations.

## Requirements

1. **Maintainability**: Developers should easily understand and update documentation tags
2. **Automation**: Documentation should regenerate automatically when code changes
3. **Quality**: Generated docs should be high-quality, accurate, and well-structured
4. **Practicality**: Implementation should be achievable with current team/resources
5. **Scalability**: Should work across 8+ interconnected Python packages

## The 5 Approaches

See the full analysis in: `docs/standards/SELF_DOCUMENTING_CODE.md`

**Quick Summary:**

1. **Decorator-Based** - Use `@document_in("MANIFESTO.md")` decorators on classes/methods
2. **Docstring Convention** - Use structured sections in docstrings (Manifesto:, Features:, Architecture:)
3. **EntitySpine Graph** - Model documentation as entities/relationships in knowledge graph
4. **LLM-Assisted** - Code provides structure, LLM generates prose and diagrams
5. **Hybrid** - Combine decorators + graph + LLM with human review

## Your Task

Analyze each approach and recommend:

1. **Primary Recommendation**: Which approach should we implement first?
2. **Reasoning**: Why this approach is best for this specific use case
3. **Implementation Plan**: 4-week roadmap to MVP
4. **Evolution Path**: How to evolve from Phase 1 → Phase 2 → Phase 3
5. **Risk Mitigation**: What could go wrong and how to prevent it
6. **Success Metrics**: How to measure if this is working

## Constraints

- Team: 1 senior developer, willing to invest time
- Stack: Python 3.11+, can add dependencies if they provide real value
- Timeline: Build it right - willing to take 8-12 weeks for proper foundation
- Existing codebase: ~15,000 lines across 8 packages
- Documentation debt: ~20 markdown files with duplicates and staleness
- **Philosophy**: Build the foundation properly, not just quick hacks

## Scoring Criteria

Rate each approach (1-10) on:

| Criterion | Weight | Decorator | Docstring | Graph | LLM | Hybrid |
|-----------|--------|-----------|-----------|-------|-----|--------|
| **Proper Foundation** (extensible architecture) | 25% | ? | ? | ? | ? | ? |
| **Long-term Maintainability** (5-year horizon) | 20% | ? | ? | ? | ? | ? |
| **Code Clarity** (doesn't pollute codebase) | 20% | ? | ? | ? | ? | ? |
| **Automation** (truly auto-updates) | 15% | ? | ? | ? | ? | ? |
| **Quality** (output quality) | 10% | ? | ? | ? | ? | ? |
| **Scalability** (handles 100+ classes) | 10% | ? | ? | ? | ? | ? |
| **TOTAL SCORE** | 100% | ? | ? | ? | ? | ? |

## Output Format

```markdown
# Self-Documenting Code: Recommendation

## Executive Summary
[2-3 sentences: Which approach to use and why]

## Primary Recommendation: [Approach Name]

### Why This Approach?
[3-4 key reasons this is the best fit]

### Scored Analysis

| Criterion | Score | Reasoning |
|-----------|-------|-----------|
| Proper Foundation | ?/10 | ... |
| Long-term Maintainability | ?/10 | ... |
| Code Clarity | ?/10 | ... |
| Automation | ?/10 | ... |
| Quality | ?/10 | ... |
| Scalability | ?/10 | ... |
| **TOTAL** | **?/100** | |

### 12-Week Foundation-First Implementation Plan

#### Phase 1: Architecture & Core (Weeks 1-4)
- [ ] Design extensible plugin architecture
- [ ] Build AST/docstring parser framework
- [ ] Create abstract document model (sections, metadata, relationships)
- [ ] Implement template engine with Jinja2
- [ ] Unit tests for core extraction logic

**Deliverable:** Solid foundation that can support multiple documentation formats

#### Phase 2: First Integration (Weeks 5-8)
- [ ] Implement primary approach (decorators/docstrings/etc)
- [ ] Integrate with 3-5 core classes as proof-of-concept
- [ ] Build CLI tool (`docbuilder build`)
- [ ] Generate first auto-docs (MANIFESTO.md or FEATURES.md)
- [ ] CI/CD integration (pre-commit hooks)

**Deliverable:** Working system generating real documentation from annotated code

#### Phase 3: Enhancement & Scale (Weeks 9-12)
- [ ] Add LLM integration for diagrams/prose enhancement
- [ ] Extend to all 8 packages
- [ ] Build validation framework (docs ↔ code consistency checks)
- [ ] Add caching/incremental builds
- [ ] Documentation for contributors

**Deliverable:** Production-ready system with 80%+ documentation coverage

### Long-Term Evolution Path

**Phase 1 (Months 1-3):** Foundation
- Build proper architecture (parser → model → renderer)
- Support one documentation type well
- Prove concept with real code

**Phase 2 (Months 4-6):** Enhancement
- Add LLM assistance (diagrams, prose polish)
- Support multiple doc formats (API docs, architecture, guides)
- Build contributor workflow

**Phase 3 (Months 7-12):** Ecosystem
- Extract as standalone tool (open source?)
- Add plugin system for custom renderers
- Support other languages (TypeScript, Java)
- Build doc quality metrics dashboard

### Risks & Mitigation

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| [Risk 1] | High/Med/Low | High/Med/Low | [Strategy] |
| [Risk 2] | ... | ... | ... |

### Success Metrics

**Month 1 Checkpoint:**
- [ ] Parser framework complete with tests
- [ ] Can extract structured data from 5+ classes
- [ ] Template system rendering one document type
- [ ] Architecture reviewed and validated

**Month 3 Goal:**
- [ ] One complete documentation type auto-generated (MANIFESTO.md)
- [ ] CI/CD integration preventing stale docs
- [ ] 20+ classes using annotation system
- [ ] Developer adoption (team using it naturally)

**Month 6 Vision:**
- [ ] All 8 packages using self-doc system
- [ ] Multiple doc types (manifesto, features, API, architecture)
- [ ] LLM integration for diagrams
- [ ] Zero manual documentation maintenance

**Year 1 Vision:**
- [ ] System extracted as standalone tool
- [ ] Used across multiple projects
- [ ] Community contributions
- [ ] Documentation quality measurably improved

### What NOT to Do

1. **Anti-pattern 1: Over-engineering the first version** - Start simple, but with good architecture
2. **Anti-pattern 2: Tight coupling to one doc format** - Build abstraction layer from day 1
3. **Anti-pattern 3: Ignoring the developer experience** - If it's painful to use, it won't get adopted
4. **Anti-pattern 4: No validation layer** - Must catch docs/code drift automatically
5. **Anti-pattern 5: Skipping the architecture phase** - Spend week 1 designing properly

### Architectural Principles

The recommended approach should follow these principles:

1. **Separation of Concerns**
   - Parser (extract from code) → Model (structured data) → Renderer (generate docs)
   - Each layer testable independently

2. **Extensibility**
   - Plugin architecture for new doc types
   - Support multiple annotation styles
   - Easy to add LLM/tool integrations

3. **Developer Experience**
   - Minimal code pollution
   - Clear error messages
   - Fast incremental builds
   - Preview mode for rapid iteration

4. **Quality Assurance**
   - Auto-validation (docs ↔ code consistency)
   - Pre-commit hooks prevent stale docs
   - Test coverage for extraction logic
   - Lint rules for annotation format

### Quick Start Example

```python
# Example of how a developer would use this system

# Before (manual docs):
class EntityResolver:
    """Resolves entities."""  # Then manually update MANIFESTO.md

# After (self-documenting):
[Show concrete code example of your recommended approach]
```

### Code Sample: Parser/Generator

```python
# Minimal working example of the extraction/generation logic
[50-100 lines showing core mechanism]
```

## Alternative Approaches Considered

### Runner-Up: [Approach Name]
**Why not first?** [2-3 sentences]
**When to use it:** [Specific scenario]

### Rejected: [Approach Name]
**Why rejected?** [2-3 sentences]

## Final Recommendation

Start with: **[Approach Name]**

Because: [1 compelling sentence about why this builds the best foundation]

**Week 1 Priority:** Design the Parser → Model → Renderer architecture

**Month 1 Goal:** Build extensible foundation with proper abstractions

**Month 3 Milestone:** First production documentation auto-generated

If you can only do ONE thing to start, do: **[Specific architectural decision]**
```

## Additional Context

**Current Pain Points:**
- Documentation has duplicates (entityspine/docs/MANIFESTO.md vs entityspine/docs/architecture/MANIFESTO.md)
- ~20 historical planning docs need archiving
- No clear documentation ownership
- Docs lag behind code by weeks

**Ideal End State:**
- `git commit` → docs auto-regenerate in CI/CD
- MANIFESTO.md always reflects current code structure
- Architecture diagrams auto-update when classes change
- Zero manual doc maintenance

**Technology Preferences:**
- Prefer stdlib when possible
- OK with optional dependencies for tooling
- Already using: MkDocs, pytest, ruff
- Open to: Jinja2 templates, AST parsing, LLM APIs

## Your Response

Provide the complete analysis in the format above. Be opinionated, specific, and actionable. Assume I will implement your recommendation verbatim, so make it detailed and practical.
