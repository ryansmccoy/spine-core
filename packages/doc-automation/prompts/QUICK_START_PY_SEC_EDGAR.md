# 📋 COPY-PASTE PROMPT: Annotate py-sec-edgar Classes

**Copy everything below and send to an LLM with file editing access:**

---

## TASK: Add Extended Docstrings to py-sec-edgar Classes

You are a documentation automation agent. Add rich extended docstrings to Python classes in the py-sec-edgar project.

### Project Context

**py-sec-edgar** is a Python library for downloading and parsing SEC EDGAR filings.

**The Project Origin (Why It Exists):**
The project started in **2018** as a tool to download SEC filings programmatically. The fundamental problem: SEC EDGAR has millions of filings, but accessing them requires understanding complex URL patterns, handling rate limits, parsing multiple formats (SGML, HTML, XBRL), and extracting meaningful data. Over the years it evolved from simple downloading to full extraction pipelines with LLM-powered analysis, exhibit parsing, and EntitySpine integration for company resolution.

**Core Principles (use in Manifesto sections):**
1. **SEC-first** - Built specifically for SEC EDGAR's quirks (rate limits, file formats, accession numbers)
2. **Form-aware** - Different forms (10-K, 8-K, DEF 14A) need different parsing strategies
3. **Exhibit extraction** - Exhibits (21, 99, EX-*) contain critical data hidden in filings
4. **Identity resolution** - CIK → Company → Ticker via EntitySpine integration
5. **LLM-enhanced** - Modern extraction uses LLMs for unstructured content

### Extended Docstring Format

```python
class ClassName:
    """
    One-line summary.
    
    Extended description (2-3 sentences).
    
    Manifesto:
        Why this class exists. Reference SEC EDGAR specifics.
        Explain form-specific handling if applicable.
    
    Architecture:
        ```
        SEC EDGAR → Download → Parse → Extract → Store
        ```
        Dependencies: requests, beautifulsoup4, etc.
        Rate Limit: SEC requires 10 req/sec max
    
    Features:
        - Feature 1
        - Feature 2
    
    Examples:
        >>> client = SECClient()
        >>> filing = client.get_filing(cik="320193", form="10-K")
    
    Performance:
        - Download: ~500ms (rate-limited)
        - Parse: ~50ms per filing
    
    Guardrails:
        - Do NOT exceed SEC rate limits (10 req/sec)
          ✅ Instead: Use built-in rate limiting
    
    Tags:
        - sec_edgar
        - filing_parser
    
    Doc-Types:
        - MANIFESTO (section: "SEC Access", priority: 10)
        - FEATURES (section: "Parsing", priority: 9)
    """
```

### Files to Annotate (Feature-Based + Chronological Order)

**Selection methodology**: Organized by feature importance, following the project's 7-year evolution from basic downloading (2018) through LLM extraction (2026).

---

## 🔴 PHASE 1: SEC CLIENT & DOWNLOADS - The Original Core (2018 - Do First)

*The original purpose: download filings from SEC EDGAR*

| Order | File | Classes | Why First |
|-------|------|---------|-----------|
| 1 | `sec.py` | SEC | **THE CLIENT** - main SEC EDGAR access class |
| 2 | `client/http.py` | HTTPClient | HTTP client with rate limiting |
| 3 | `download/result.py` | DownloadResult, DownloadStatus | Download outcomes |
| 4 | `adapters/sec_api.py` | SECAPIAdapter, FilingFetcher (7) | SEC API adapters |
| 5 | `adapters/sec_feeds.py` | DailyFeed, FullIndexFeed (4) | SEC index feeds |

---

## 🟠 PHASE 2: CORE INFRASTRUCTURE - Exceptions, Results, Config

*Foundational types used throughout the codebase*

| Order | File | Classes | Feature |
|-------|------|---------|---------|
| 6 | `core/exceptions.py` | SECError, RateLimitError, ParseError (12) | Exception hierarchy |
| 7 | `core/results.py` | Result, Ok, Err (9) | Result pattern (like EntitySpine) |
| 8 | `core/reference/periods.py` | FiscalPeriod, Quarter (4) | Fiscal period handling |
| 9 | `interfaces.py` | Extractor, Parser, Storage (5) | Core protocols |

---

## 🟡 PHASE 3: FORMS - Form-Specific Parsing

*Different SEC forms require different parsing strategies*

| Order | File | Classes | Form Type |
|-------|------|---------|-----------|
| 10 | `forms/models.py` | FilingMetadata, Section, Exhibit (12) | Core filing models |
| 11 | `forms/base.py` | BaseFormParser, FormRegistry (7) | Form parser base |
| 12 | `forms/form10k.py` | Form10KParser (2) | 10-K (annual report) |
| 13 | `forms/form8k.py` | Form8KParser (2) | 8-K (current report) |

---

## 🟢 PHASE 4: EXHIBITS - The Hidden Value (Critical Feature)

*Exhibits contain critical data: subsidiaries (Ex-21), contracts (Ex-10), press releases (Ex-99)*

| Order | File | Classes | Feature |
|-------|------|---------|---------|
| 14 | `exhibits/models.py` | Exhibit, ExhibitType, ExhibitContent (15) | **EXHIBIT MODELS** |
| 15 | `exhibits/base.py` | BaseExhibitExtractor (5) | Exhibit extractor base |
| 16 | `exhibits/service.py` | ExhibitService (4) | Exhibit extraction service |
| 17 | `exhibits/adapters/entityspine.py` | EntitySpineAdapter (3) | EntitySpine integration |

---

## 🔵 PHASE 5: INTELLIGENCE - LLM-Powered Extraction (2026)

*Modern extraction using LLMs for unstructured content*

| Order | File | Classes | Feature |
|-------|------|---------|---------|
| 18 | `intelligence/schemas.py` | ExtractionSchema, FieldSpec (16) | **LLM SCHEMAS** |
| 19 | `extractor/submission_parser.py` | SubmissionParser (4) | Parse submission.txt |
| 20 | `storage/extraction_models.py` | ExtractionResult, ExtractedField (5) | Extraction storage |

---

## 🟣 PHASE 6: COMPANIES & IDENTITY - Who Filed What?

*Company resolution: CIK → Name → Ticker*

| Order | File | Classes | Feature |
|-------|------|---------|---------|
| 21 | `companies/models.py` | Company, Filer (8) | Company models |
| 22 | `companies/service.py` | CompanyService (5) | Company lookup service |
| 23 | `core/identity/entity.py` | IdentityEntity (4) | Identity resolution |
| 24 | `core/identity/enricher.py` | IdentityEnricher (4) | Enrich with identifiers |

---

## ⚪ PHASE 7: SERVICES & STORAGE

*Query services, storage backends, scheduling*

| Order | File | Classes | Feature |
|-------|------|---------|---------|
| 25 | `services/query_service.py` | QueryService (7) | Filing queries |
| 26 | `services/checkpoint.py` | Checkpoint, CheckpointStore (4) | Resume interrupted jobs |
| 27 | `services/strategy.py` | DownloadStrategy (4) | Download strategies |
| 28 | `graph/storage.py` | GraphStorage (10) | Knowledge graph storage |
| 29 | `graph/queries.py` | GraphQuery (4) | Graph queries |
| 30 | `scheduler/scheduler.py` | Scheduler (4) | Job scheduling |
| 31 | `notifiers/sec_notifier.py` | SECNotifier (8) | Filing notifications |
| 32 | `api/app.py` | create_app, APIRoutes (7) | FastAPI application |

---

### Workflow

**Work in PHASES, not random files:**
1. Complete Phase 1 entirely (5 files) - the core SEC download functionality
2. Complete Phase 2 entirely (4 files) - foundational types
3. Then proceed to Phase 3, 4, etc.

For each file:
1. Read the entire source file
2. Add extended docstrings to **all public classes**
3. Ensure Manifesto references SEC EDGAR specifics (rate limits, form types, etc.)

### Quality Checklist (per phase)
- [ ] All classes in the phase are annotated
- [ ] Manifesto explains SEC EDGAR context
- [ ] Architecture shows: SEC EDGAR → Download → Parse → Extract
- [ ] Examples show typical SEC access patterns

### Start Now

**Begin with Phase 1, File 1: `sec.py`** - the main SEC client class that started it all in 2018. This is THE entry point for accessing SEC EDGAR.

---

**When done with each phase, report progress before continuing.**
