# 🤖 GenAI-Spine - Annotation Guide

**Project-Specific Guide for Annotating GenAI-Spine Classes**

*For use with Documentation Automation Package - February 2026*

---

## 📋 PROJECT CONTEXT

### What is GenAI-Spine?

**GenAI-Spine** is a unified, provider-agnostic LLM service for the entire Spine ecosystem:

> *"I need chat, summarization, extraction, classification, rewriting, and prompt management across Ollama, OpenAI, and Anthropic without changing code"*

### Core Philosophy

**Principle #1: Provider Agnostic**

Write once, run on any LLM provider:
- **Ollama** - Local, privacy-first, free
- **OpenAI** - GPT-4, GPT-3.5, state-of-the-art
- **Anthropic** - Claude, constitutional AI

Swap providers with config change, not code change.

**Principle #2: OpenAI-Compatible API**

Follow OpenAI API conventions:
- `/v1/chat/completions` - Chat interface
- `/v1/completions` - Text completion
- `/v1/models` - List available models

Drop-in replacement for OpenAI SDK.

**Principle #3: Cost Tracking Built-In**

Every API call tracks:
- Tokens used (input/output)
- Estimated cost ($)
- Provider used
- Model used
- Timestamp

Aggregate by day, week, month, provider, model.

**Principle #4: Prompt Management as First-Class Feature**

Prompts are versioned templates:
- CRUD operations (create, read, update, delete)
- Versioning (track changes over time)
- Variables (template substitution)
- Execute by ID or name

Example:
```python
# Create prompt template
prompt_id = await client.create_prompt(
    name="summarize_article",
    template="Summarize this article in {{max_words}} words:\n\n{{content}}",
    variables={"max_words": "100", "content": ""}
)

# Execute with variables
result = await client.execute_prompt(
    prompt_id=prompt_id,
    variables={"max_words": "50", "content": article_text}
)
```

**Principle #5: Ecosystem Integration**

Reuses types from sibling packages:
- `Result[T]`, `Ok`, `Err` from EntitySpine
- `ExecutionContext` for tracing
- `ErrorCategory` for error handling

Consistency across all Spine projects.

### Key Concepts

1. **Provider** - LLM service (Ollama, OpenAI, Anthropic)
2. **Model** - Specific LLM (llama3.2, gpt-4, claude-3-opus)
3. **Capability** - High-level task (summarize, extract, classify, rewrite)
4. **Prompt Template** - Versioned, parameterized prompt
5. **Execution Context** - Tracing/logging context (workflow name, parent context)
6. **Usage Tracking** - Token counts, costs, provider/model stats

### Architecture Patterns

1. **Adapter Pattern** - Abstract provider differences (Ollama vs OpenAI)
2. **Strategy Pattern** - Swap providers at runtime
3. **Template Method** - Base capability implementation with hooks
4. **Facade** - Simple API over complex LLM interactions

---

## 🎯 CLASSES TO ANNOTATE

### **Tier 1 (MUST Annotate - 15 classes)**

Core abstractions, provider implementations, and high-value capabilities.

#### 🔴 Provider Layer (`providers/`) - **CRITICAL - CORE ARCHITECTURE**

| Class | File | Priority | Why |
|-------|------|----------|-----|
| `LLMProvider` | `providers/base.py` | **10** | Abstract base class - ALL providers implement this |
| `OllamaProvider` | `providers/ollama.py` | **10** | Local/privacy-first provider implementation |
| `OpenAIProvider` | `providers/openai.py` | **10** | GPT-4/3.5 provider implementation |
| `AnthropicProvider` | `providers/anthropic.py` | **10** | Claude provider implementation |
| `ProviderRegistry` | `providers/registry.py` | **10** | Discover and instantiate providers at runtime |

These classes ARE the provider-agnostic architecture. They must be annotated to explain:
- How the adapter pattern enables provider swapping
- Request/response translation per provider
- Cost tracking integration
- Streaming implementation differences

#### Settings & Configuration

| Class | File | Priority | Why |
|-------|------|----------|-----|
| `Settings` | `settings.py` | **10** | Configures providers, models, API keys, costs |

#### Core API Models

| Class | File | Priority | Why |
|-------|------|----------|-----|
| `ChatCompletionRequest` | `api/routers/chat.py` | **10** | OpenAI-compatible chat request |
| `ChatCompletionResponse` | `api/routers/chat.py` | **10** | OpenAI-compatible chat response |

#### Capabilities (High-Level Tasks)

| Class | File | Priority | Why |
|-------|------|----------|-----|
| `SummarizeRequest/Response` | `api/routers/capabilities.py` | **10** | Most common LLM task |
| `ExtractRequest/Response` | `api/routers/capabilities.py` | 9 | Structured data extraction |
| `ClassifyRequest/Response` | `api/routers/capabilities.py` | 9 | Content categorization |

#### Prompt Management

| Class | File | Priority | Why |
|-------|------|----------|-----|
| `PromptCreateRequest` | `api/routers/prompts.py` | **10** | First-class prompt management |
| `PromptResponse` | `api/routers/prompts.py` | **10** | Prompt retrieval model |

#### Usage & Cost Tracking

| Class | File | Priority | Why |
|-------|------|----------|-----|
| `UsageResponse` | `api/routers/usage.py` | 9 | Cost tracking built-in |

---

### **Tier 2 (SHOULD Annotate - 20 classes)**

Supporting features and specialized capabilities.

#### Storage Layer (`storage/`)
- `Prompt` - Prompt entity model
- `PromptVersion` - Version tracking
- `Execution` - Execution record
- `DailyCost` - Cost aggregation
- `UserLLMConfig` - Per-user config

#### Repository Protocols (`storage/protocols/`)
- `PromptRepository` - Prompt CRUD protocol
- `ExecutionRepository` - Execution logging protocol
- `UnitOfWork` - Transaction management
- `StorageBackend` - Storage abstraction

#### API Models - Sessions
- `SessionCreateRequest/Response` - Multi-turn conversations
- `MessageSendRequest/Response` - Send messages to sessions

#### API Models - Commit
- `GenerateCommitRequest/Response` - Git commit messages
- `FileChange`, `FeatureGroup` - Diff analysis models

#### API Models - Completions
- `CompletionRequestBody/Response` - Non-chat completions

#### API Models - Rewrite
- `RewriteRequest/Response` - Text transformation
- `InferTitleRequest/Response` - Title generation

#### API Models - Execute
- `ExecutePromptRequest/Response` - Run prompt templates

---

### **Tier 3 (NICE TO HAVE - 50+ classes)**

Supporting utilities, error classes, validation helpers.

- All Pydantic schemas in `api/routers/`
- Internal utility classes
- Error classes and exceptions

---

## 📝 PROJECT-SPECIFIC ANNOTATION GUIDELINES

### Provider Pattern - THE Core Architecture

The `providers/` directory implements the provider-agnostic pattern:

```python
# providers/base.py - Abstract base
class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.
    
    All providers (Ollama, OpenAI, Anthropic) implement this interface,
    enabling seamless swapping via configuration.
    
    Manifesto:
        Provider-agnostic design is THE core principle of GenAI-Spine.
        
        Swap from Ollama → OpenAI → Anthropic with config change, not
        code change. This abstract class defines the contract that ALL
        providers must implement.
    """
    
    @abstractmethod
    async def chat(self, request: ChatRequest) -> ChatResponse: ...
    
    @abstractmethod  
    async def complete(self, prompt: str) -> str: ...

# providers/ollama.py - Concrete implementation
class OllamaProvider(LLMProvider):
    """Local, privacy-first provider."""

# providers/openai.py
class OpenAIProvider(LLMProvider):
    """OpenAI GPT-4/3.5 provider."""

# providers/anthropic.py
class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider."""

# providers/registry.py
class ProviderRegistry:
    """Discover and instantiate providers at runtime."""
```

**When annotating providers:**
- Explain how they implement `LLMProvider` contract
- Document provider-specific quirks (streaming, token counting)
- Include cost information per model
- Show configuration examples

### Manifesto Section - Emphasize These Principles

For GenAI-Spine classes:

```python
Manifesto:
    Provider-agnostic design means you can swap from Ollama to
    OpenAI to Anthropic with a config change, not a code change.
    
    [For API classes]
    OpenAI-compatible API provides drop-in replacement for OpenAI SDK.
    Use the same /v1/chat/completions endpoint, same request/response
    format, same client libraries.
    
    [For capabilities]
    High-level capabilities (summarize, extract, classify) abstract
    away prompt engineering complexity. Users describe WHAT they want,
    not HOW to prompt the LLM.
    
    [For prompt management]
    Prompts are first-class assets:
    - Versioned (track changes over time)
    - Templated (variables for reuse)
    - Executable (run by ID or name)
    - Auditable (who created, when, why)
    
    [For cost tracking]
    Every API call tracks tokens and costs. No surprises on your
    cloud bill. Aggregate by provider, model, day, user.
    
    [For ecosystem integration]
    Reuses EntitySpine types (Result[T], ExecutionContext) for
    consistency across all Spine projects.
```

### Architecture Section - Provider Abstraction

```python
Architecture:
    ```
    Client Request
          ↓
    ┌─────────────────────────┐
    │  GenAI Spine API        │
    │  (FastAPI)              │
    └─────────┬───────────────┘
              ↓
    ┌─────────────────────────┐
    │  Provider Router:       │
    │  if model.startswith(   │
    │    "gpt"): OpenAI       │
    │  elif "claude": Anthropic│
    │  else: Ollama           │
    └─────────┬───────────────┘
              ↓
    ┌─────────────────────────┐
    │  Provider Adapter       │
    │  - Translate request    │
    │  - Call provider API    │
    │  - Parse response       │
    │  - Track usage          │
    └─────────┬───────────────┘
              ↓
    ┌─────────────────────────┐
    │  Usage Tracker          │
    │  - Log tokens           │
    │  - Estimate cost        │
    │  - Store metrics        │
    └─────────────────────────┘
    ```
    
    Request Flow: API → Router → Adapter → Provider
    Response Flow: Provider → Adapter → Tracker → API
    
    Providers: Ollama (local), OpenAI (cloud), Anthropic (cloud)
    Protocols: HTTP/REST, streaming (SSE)
```

### Features Section - Capability Highlights

```python
Features:
    - 25+ API endpoints (chat, summarize, extract, classify, rewrite)
    - Multi-provider support (Ollama, OpenAI, Anthropic)
    - OpenAI-compatible API (/v1/chat/completions)
    - Cost tracking (per-request, aggregated by day/provider/model)
    - Prompt management (CRUD, versioning, templates)
    - Streaming responses (SSE for real-time output)
    - Session management (multi-turn conversations)
    - Commit message generation (analyze git diffs)
    - Title inference (auto-generate from content)
    - Batch processing (multiple requests in parallel)
```

### Guardrails Section - Common GenAI Mistakes

```python
Guardrails:
    - Do NOT hardcode provider/model
      ✅ Instead: Accept provider/model as parameters, use config
    
    - Do NOT skip usage tracking
      ✅ Instead: Always log tokens/costs (prevents bill surprises)
    
    - Do NOT reinvent prompt engineering for every task
      ✅ Instead: Use high-level capabilities (summarize, extract)
    
    - Do NOT assume OpenAI is the only provider
      ✅ Instead: Design for provider-agnostic abstractions
    
    - Do NOT expose raw API keys in responses
      ✅ Instead: Redact sensitive data, use env vars
    
    - ALWAYS validate prompt templates before execution
      (Prevent prompt injection, validate variable substitution)
```

### Tags - Use These GenAI-Specific Tags

Required tags by domain:
- **Core**: `core_concept`, `provider_agnostic`, `openai_compatible`
- **Providers**: `ollama`, `openai`, `anthropic`, `provider_adapter`
- **Capabilities**: `capability`, `summarization`, `extraction`, `classification`, `rewriting`, `generation`
- **API**: `core_api`, `chat`, `completions`, `streaming`
- **Prompts**: `prompt_management`, `templates`, `versioning`, `variables`
- **Costs**: `cost_tracking`, `usage_tracking`, `metrics`, `tokens`
- **Ecosystem**: `ecosystem_integration`, `result_type`, `execution_context`

### Doc-Types - Where GenAI Classes Should Appear

```python
Doc-Types:
    - MANIFESTO (section: "Provider Agnostic", priority: 10)
      # For classes about provider abstraction
    
    - FEATURES (section: "LLM Capabilities", priority: 10)
      # For summarize, extract, classify, rewrite
    
    - FEATURES (section: "Prompt Management", priority: 9)
      # For prompt CRUD, versioning, execution
    
    - ARCHITECTURE (section: "Provider Integration", priority: 9)
      # For adapter pattern, provider routing
    
    - API_REFERENCE (section: "Core APIs", priority: 10)
      # For OpenAI-compatible endpoints
    
    - UNIFIED_DATA_MODEL (section: "Shared Types", priority: 8)
      # For Result[T], ExecutionContext integration
```

### Ecosystem Integration Annotations

If a class uses EntitySpine types:

```python
Ecosystem-Integration:
    Package: entityspine
    Types-Used:
    - Result[T]: For error handling (Ok/Err)
    - ExecutionContext: For tracing (parent/child contexts)
    - ErrorCategory: For categorizing failures
    
    Rationale:
    Consistency across Spine ecosystem. All packages use same
    Result type for error handling, same ExecutionContext for
    tracing, same ErrorCategory for error classification.
    
    Example:
    ```python
    from genai_spine.compat import Result, Ok, Err, ExecutionContext
    
    result: Result[str] = Ok("success")
    ctx = ExecutionContext(workflow_name="summarize")
    ```
    
    See: docs/ECOSYSTEM_INTEGRATION.md
```

---

## 📚 REFERENCE DOCUMENTS

### Must Read Before Annotating

1. **GenAI-Spine README**: `genai-spine/README.md`
   - Overview, quick start, ecosystem integration

2. **Ecosystem Integration**: `genai-spine/docs/ECOSYSTEM_INTEGRATION.md`
   - Type mapping from EntitySpine
   - Result[T], ExecutionContext patterns

3. **Capture Spine Integration**: `genai-spine/docs/CAPTURE_SPINE_INTEGRATION.md`
   - How Capture Spine uses GenAI features

4. **Capabilities**: `genai-spine/docs/capabilities/`
   - Capability tiers (Tier 1, 2, 3, 4)

### Example Annotated Class (Full Template)

```python
from pydantic import BaseModel, Field
from typing import List, Literal

class SummarizeRequest(BaseModel):
    """
    Request to summarize content using an LLM.
    
    High-level capability that abstracts prompt engineering complexity.
    Users specify content and constraints, GenAI handles the rest.
    
    Manifesto:
        High-level capabilities (summarize, extract, classify) free
        users from prompt engineering.
        
        Instead of:
        ```python
        client.chat("Summarize this in 100 words: {content}")
        ```
        
        Users write:
        ```python
        client.summarize(content, max_words=100)
        ```
        
        Benefits:
        - Consistent results (tuned prompts)
        - Less cognitive load (no prompt design)
        - Provider-agnostic (same code, any LLM)
        - Versioned prompts (track improvements)
        
        Provider-agnostic design: Works with Ollama (local, free),
        OpenAI (GPT-4, state-of-the-art), or Anthropic (Claude).
        Swap with config change.
    
    Architecture:
        ```
        User Code
              ↓
        POST /v1/capabilities/summarize
              ↓
        SummarizeRequest validation (Pydantic)
              ↓
        Prompt Template:
        "Summarize this content in {{max_words}} words.
         Focus on {{focus}} if provided.
         
         Content: {{content}}"
              ↓
        Provider Router (detect model → provider)
              ↓
        Provider Adapter (OpenAI/Ollama/Anthropic)
              ↓
        LLM Response
              ↓
        Usage Tracker (log tokens, cost)
              ↓
        SummarizeResponse
        ```
        
        Validation: Pydantic (type checking, constraints)
        Prompt: Jinja2 templates with variables
        Routing: Model prefix detection (gpt→OpenAI, llama→Ollama)
        Tracking: Every call logged with tokens/cost
    
    Features:
        - Auto-detect provider from model name
        - Customizable summary length (max_words, max_sentences)
        - Focus parameter (emphasize specific aspects)
        - Bullet points or paragraph format
        - Multiple summary styles (brief, detailed, technical)
        - Cost estimation before execution
        - Streaming support (real-time output)
    
    Examples:
        >>> from genai_spine import GenAIClient
        >>> 
        >>> client = GenAIClient()
        >>> 
        >>> # Basic summarization
        >>> summary = await client.summarize(
        ...     content="Long article text here...",
        ...     max_words=100
        ... )
        >>> print(summary.text)
        "This article discusses..."
        
        # With focus
        >>> summary = await client.summarize(
        ...     content=sec_filing_text,
        ...     max_words=150,
        ...     focus="financial results"
        ... )
        
        # Bullet points
        >>> summary = await client.summarize(
        ...     content=research_paper,
        ...     format="bullets",
        ...     max_bullets=5
        ... )
        
        # Different provider
        >>> summary = await client.summarize(
        ...     content=article,
        ...     model="claude-3-opus"  # Uses Anthropic
        ... )
    
    Performance:
        - Latency: 500ms-3s (model-dependent)
          - Ollama (local): 1-2s
          - OpenAI (cloud): 500ms-1s
          - Anthropic (cloud): 1-2s
        - Throughput: 10-50 requests/sec (provider-limited)
        - Cost: $0.001-$0.01 per summary (model-dependent)
        - Token usage: 100-500 tokens (content-dependent)
    
    Guardrails:
        - Do NOT send PII/sensitive data without review
          ✅ Instead: Redact before sending, use local Ollama
        
        - Do NOT assume unlimited API quota
          ✅ Instead: Check usage stats, set rate limits
        
        - Do NOT ignore max_tokens limit
          ✅ Instead: Chunk large content, summarize in parts
        
        - Do NOT hardcode provider/model
          ✅ Instead: Accept as parameter, use config
        
        - ALWAYS validate content length (prevent token overflow)
          (Truncate or chunk if > max context window)
    
    Context:
        Problem: Every app needs summarization, but prompt engineering
        is hard, inconsistent, and provider-specific.
        
        Solution: High-level /v1/capabilities/summarize endpoint with
        tuned prompts, provider abstraction, and cost tracking.
        
        Alternatives Considered:
        - Raw chat API: Too low-level, inconsistent results
        - LangChain: Heavy dependency, over-engineered
        - Provider-specific SDKs: No abstraction, lock-in
        
        Why This Approach:
        - Simple API (users describe intent, not implementation)
        - Provider-agnostic (swap providers without code change)
        - Cost-aware (track spending, estimate before execution)
        - Production-ready (validation, error handling, metrics)
    
    Changelog:
        - v0.1.0: Initial summarize capability
        - v0.2.0: Added focus parameter
        - v0.3.0: Added bullet point format
        - v0.4.0: Provider-agnostic (Ollama, OpenAI, Anthropic)
        - v0.5.0: Cost estimation and tracking
    
    Feature-Guide:
        Target: guides/CAPABILITIES_GUIDE.md
        Section: "Summarization"
        Include-Example: True
        Priority: 10
    
    Architecture-Doc:
        Target: architecture/CAPABILITIES_ARCHITECTURE.md
        Section: "High-Level Capabilities"
        Diagram-Type: sequence
    
    Ecosystem-Integration:
        Package: entityspine
        Types-Used:
        - Result[T]: Return Ok(summary) or Err(error)
        - ExecutionContext: Trace summarization workflow
        
        Example:
        ```python
        from genai_spine.compat import Result, Ok, Err
        
        result: Result[SummarizeResponse] = await summarize(...)
        match result:
            case Ok(summary):
                print(summary.text)
            case Err(error):
                logger.error(f"Summarization failed: {error}")
        ```
    
    Tags:
        - capability
        - summarization
        - high_level_api
        - provider_agnostic
        - openai_compatible
        - cost_tracking
    
    Doc-Types:
        - MANIFESTO (section: "High-Level Capabilities", priority: 9)
        - FEATURES (section: "LLM Capabilities", priority: 10)
        - ARCHITECTURE (section: "Capabilities", priority: 9)
        - API_REFERENCE (section: "Capabilities API", priority: 10)
    """
    
    content: str = Field(..., description="Content to summarize")
    max_words: int = Field(100, gt=0, le=500, description="Max words in summary")
    focus: str | None = Field(None, description="Aspect to emphasize")
    format: Literal["paragraph", "bullets"] = Field("paragraph")
    model: str = Field("llama3.2:latest", description="LLM model to use")
```

---

## ✅ VALIDATION CHECKLIST

Before submitting annotated GenAI-Spine classes:

### Content Requirements
- [ ] Manifesto explains provider-agnostic design
- [ ] Manifesto mentions high-level capabilities (if applicable)
- [ ] Architecture includes provider routing diagram
- [ ] Architecture notes cost tracking
- [ ] Features list provider options (Ollama, OpenAI, Anthropic)
- [ ] Examples show OpenAI-compatible usage
- [ ] Guardrails warn about PII/sensitive data
- [ ] Tags include GenAI-specific tags
- [ ] Ecosystem integration noted (Result[T], ExecutionContext)

### GenAI-Specific
- [ ] Uses correct terminology (provider, model, capability)
- [ ] References OpenAI compatibility
- [ ] Mentions cost tracking
- [ ] Includes token usage estimates
- [ ] Notes streaming support (if applicable)
- [ ] References prompt management (if applicable)

### Quality
- [ ] At least 3 tags
- [ ] At least 2 doc-types
- [ ] Examples are runnable (async/await)
- [ ] No TODO or placeholder text

---

## 🚀 QUICK START

1. **Read this entire guide** (10 minutes)
2. **Read ECOSYSTEM_INTEGRATION.md** (10 minutes)
3. **Read EXTENDED_ANNOTATION_PROMPT.md** (15 minutes)
4. **Pick ONE Tier 1 class** (Settings or SummarizeRequest)
5. **Read existing code** and related docs
6. **Annotate using full extended format**
7. **Validate**: `docbuilder validate <file>`
8. **Submit for review** before batch-annotating

---

**Ready? Start with `SummarizeRequest` - it's the flagship GenAI capability!**
