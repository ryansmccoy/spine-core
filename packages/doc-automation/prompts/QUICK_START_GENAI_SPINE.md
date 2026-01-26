# 📋 COPY-PASTE PROMPT: Annotate GenAI-Spine Classes

**Copy everything below and send to an LLM with file editing access:**

---

## TASK: Add Extended Docstrings to GenAI-Spine Classes

You are a documentation automation agent. Add rich extended docstrings to Python classes in the GenAI-Spine project.

### Project Context

**GenAI-Spine** is a provider-agnostic LLM service for the Spine ecosystem.

**The Project Origin (Why It Exists):**
The project started because every Spine project (EntitySpine, FeedSpine, Capture-Spine) needed LLM capabilities, but each was implementing its own OpenAI/Ollama/Anthropic integration. GenAI-Spine centralizes this: one unified API that speaks to any LLM provider. The key insight: **your application code should not care which LLM is running** - swap Ollama for OpenAI with config, not code changes.

**Core Principles (use in Manifesto sections):**
1. **Provider-agnostic** - Swap Ollama/OpenAI/Anthropic with config, not code
2. **OpenAI-compatible API** - Drop-in replacement for OpenAI SDK
3. **Cost tracking built-in** - Every call tracks tokens and estimated cost
4. **Prompt management** - Versioned, templated, executable prompts
5. **Ecosystem integration** - Uses EntitySpine's Result[T] pattern

### Extended Docstring Format

```python
class ClassName:
    """
    One-line summary.
    
    Extended description (2-3 sentences).
    
    Manifesto:
        Why this class exists. Reference principles above.
        Explain provider-agnostic design if applicable.
    
    Architecture:
        ```
        ASCII diagram showing provider flow
        ```
        Provider: Which providers this supports
        Protocol: HTTP/REST, streaming (SSE)
    
    Features:
        - Feature 1
        - Feature 2
    
    Examples:
        >>> provider = ClassName(api_key="...")
        >>> response = await provider.chat(messages)
    
    Performance:
        - Latency: depends on provider
        - Token tracking: per-request
    
    Guardrails:
        - Do NOT hardcode provider/model
          ✅ Instead: Accept as parameters
    
    Tags:
        - provider_agnostic
        - llm_provider
    
    Doc-Types:
        - MANIFESTO (section: "Provider Agnostic", priority: 10)
        - ARCHITECTURE (section: "Provider Integration", priority: 9)
    """
```

### Files to Annotate (Feature-Based + Chronological Order)

**Selection methodology**: Organized by feature importance. GenAI-Spine was created in a single large commit (2026-01-31), so we organize by architectural layers from core outward.

---

## 🔴 PHASE 1: PROVIDERS - The Core Abstraction (Do First)

*Providers are THE point of GenAI-Spine: one interface, many LLM backends*

| Order | File | Classes | Why First |
|-------|------|---------|-----------|
| 1 | `providers/base.py` | LLMProvider | **THE INTERFACE** - ABC that all providers implement |
| 2 | `providers/ollama.py` | OllamaProvider | **LOCAL LLM** - Ollama for local models (llama2, codellama) |
| 3 | `providers/openai.py` | OpenAIProvider | **CLOUD LLM** - OpenAI (GPT-4, GPT-3.5) |
| 4 | `providers/anthropic.py` | AnthropicProvider | **CLOUD LLM** - Anthropic (Claude) |
| 5 | `providers/registry.py` | ProviderRegistry | **THE FACTORY** - creates providers by name |

---

## 🟠 PHASE 2: CAPABILITIES - What LLMs Can Do

*High-level capabilities built on top of chat completions*

| Order | File | Classes | Feature |
|-------|------|---------|---------|
| 6 | `capabilities/summarization.py` | Summarizer, SummaryConfig | **SUMMARIZE** - condense long text |
| 7 | `capabilities/extraction.py` | Extractor, ExtractionConfig | **EXTRACT** - structured data from text |
| 8 | `capabilities/classification.py` | Classifier, ClassificationConfig | **CLASSIFY** - categorize text |
| 9 | `capabilities/rewrite.py` | Rewriter, RewriteConfig | **REWRITE** - transform text style |
| 10 | `capabilities/commit.py` | CommitMessageGenerator | **COMMIT** - generate git commit messages |
| 11 | `capabilities/cost.py` | CostCalculator, TokenCounter | **COST** - track usage and estimate costs |

---

## 🟡 PHASE 3: API LAYER - FastAPI Routers

*REST API that exposes LLM capabilities*

| Order | File | Classes | Endpoint |
|-------|------|---------|----------|
| 12 | `api/app.py` | create_app | FastAPI application factory |
| 13 | `api/deps.py` | Dependencies | Dependency injection |
| 14 | `api/routers/chat.py` | ChatCompletionRequest, ChatCompletionResponse | `/v1/chat/completions` - OpenAI-compatible |
| 15 | `api/routers/completions.py` | CompletionRequest, CompletionResponse | `/v1/completions` - legacy completions |
| 16 | `api/routers/models.py` | ModelListResponse | `/v1/models` - list available models |
| 17 | `api/routers/capabilities.py` | SummarizeRequest, ExtractRequest | `/v1/summarize`, `/v1/extract` |
| 18 | `api/routers/prompts.py` | PromptCreateRequest, PromptResponse | `/v1/prompts` - prompt management |
| 19 | `api/routers/usage.py` | UsageResponse | `/v1/usage` - cost tracking |
| 20 | `api/routers/health.py` | HealthResponse | `/health` - liveness/readiness |
| 21 | `api/routers/sessions.py` | SessionCreate, SessionResponse | `/v1/sessions` - chat sessions |

---

## 🟢 PHASE 4: STORAGE - Persistence Layer

*Store prompts, usage, chat sessions*

| Order | File | Classes | Feature |
|-------|------|---------|---------|
| 22 | `storage/protocols.py` | StorageProtocol | Storage interface |
| 23 | `storage/models.py` | Prompt, Usage, ChatSession | Data models |
| 24 | `storage/sqlite.py` | SQLiteStorage | SQLite backend |
| 25 | `storage/postgres.py` | PostgresStorage | PostgreSQL backend |
| 26 | `storage/schemas.py` | PromptSchema, UsageSchema | Pydantic schemas |
| 27 | `storage/seed.py` | seed_database | Initial data seeding |

---

## 🔵 PHASE 5: CONFIGURATION & INFRASTRUCTURE

*Settings, compatibility, main entrypoint*

| Order | File | Classes | Feature |
|-------|------|---------|---------|
| 28 | `settings.py` | Settings | **CONFIG** - all configuration (providers, models, costs) |
| 29 | `compat.py` | OpenAICompat | OpenAI SDK compatibility layer |
| 30 | `main.py` | main | Uvicorn entrypoint |
| 31 | `api/tracking.py` | UsageTracker | Request/response tracking |

---

### Workflow

**Work in PHASES, not random files:**
1. Complete Phase 1 entirely (5 files) - this is the core provider abstraction
2. Complete Phase 2 entirely (6 files) - high-level capabilities
3. Then proceed to Phase 3, 4, 5

For each file:
1. Read the entire source file
2. Add extended docstrings to **all public classes**
3. Ensure Manifesto references provider-agnostic design

### Quality Checklist (per phase)
- [ ] All classes in the phase are annotated
- [ ] Manifesto explains provider-agnostic benefits
- [ ] Architecture shows: User → API → Provider → LLM Backend
- [ ] Examples show async usage patterns

### Start Now

**Begin with Phase 1, File 1: `providers/base.py`** - the `LLMProvider` ABC that defines what every provider must do. This is THE contract that enables swapping Ollama for OpenAI.

---

**When done with each phase, report progress before continuing.**
