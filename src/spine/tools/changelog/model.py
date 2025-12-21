"""Data models for the changelog generation system.

Stability: stable
Tier: none
Since: 0.4.0
Dependencies: stdlib-only
Doc-Types: API_REFERENCE
Tags: changelog, model, dataclass

Pure-stdlib dataclasses representing parsed docstring headers,
commit metadata, phase groupings, and module information.
All fields use primitive types — no Pydantic, no external deps.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

# ---------------------------------------------------------------------------
# Controlled vocabularies
# ---------------------------------------------------------------------------


class Stability(Enum):
    """Module stability level."""

    EXPERIMENTAL = "experimental"
    STABLE = "stable"
    DEPRECATED = "deprecated"


class Tier(Enum):
    """Deployment tier requirement."""

    BASIC = "basic"
    STANDARD = "standard"
    FULL = "full"
    NONE = "none"


class DocType(Enum):
    """Documentation type classification."""

    API_REFERENCE = "API_REFERENCE"
    TECHNICAL_DESIGN = "TECHNICAL_DESIGN"
    GUIDE = "GUIDE"
    TUTORIAL = "TUTORIAL"
    ADR = "ADR"
    RATIONALE = "RATIONALE"


class Impact(Enum):
    """Change impact classification."""

    PUBLIC_API = "public_api"
    INTERNAL = "internal"
    BEHAVIOR = "behavior"
    PERFORMANCE = "performance"
    DOCS = "docs"
    TESTS = "tests"
    SECURITY = "security"


class Migration(Enum):
    """Migration requirement level."""

    NONE = "none"
    MANUAL = "manual"
    AUTO = "auto"
    BREAKING = "breaking"


# Known values for validation (as lowercase sets)
VALID_STABILITY = {e.value for e in Stability}
VALID_TIER = {e.value for e in Tier}
VALID_DOC_TYPES = {e.value for e in DocType}
VALID_IMPACT = {e.value for e in Impact}
VALID_MIGRATION = {e.value for e in Migration}

VALID_FEATURE_TYPES = frozenset({
    "data_layer", "api_endpoint", "cli_command", "algorithm",
    "parser", "protocol", "infrastructure", "ui_component",
    "configuration", "testing", "documentation", "developer_tool",
    "integration", "monitoring", "security",
})

VALID_ARCHITECTURE = frozenset({
    "database", "repository_pattern", "event_sourcing", "cqrs",
    "pubsub", "async_tasks", "batch_processing", "streaming",
    "caching", "scheduling", "dependency_injection", "plugin_system",
    "middleware", "decorator_pattern", "factory_pattern",
    "strategy_pattern", "observer_pattern", "adapter_pattern",
    "orm",
})

VALID_DOMAIN = frozenset({
    "sec_filings", "financial_data", "market_data", "embeddings",
    "knowledge_graph", "entity_resolution", "text_extraction", "search",
    "operation_state", "data_quality", "workflow_orchestration",
    "llm_integration", "audit_compliance", "data_lineage",
    "feature_flags", "secrets_management", "developer_experience",
    "deployment",
})

VALID_MARKERS = frozenset({
    "NEW", "FOUNDATIONAL", "REFACTOR", "BREAKING", "DEPRECATION",
    "EXPERIMENTAL",
})


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DocHeader:
    """Parsed metadata from a module docstring header.

    Manifesto:
        Module docstrings are the single source of truth for module
        classification. Doc Headers provide machine-readable metadata
        (Stability, Tier, Doc-Types) without sacrificing human readability.
        They sit between the summary line and prose body, parsed via
        pure regex — no imports needed.

    Features:
        - Controlled vocabularies for Stability, Tier, Doc-Types
        - Frozen dataclass — immutable after parsing
        - Preserves raw text for downstream rendering
        - AST-based extraction without importing target modules

    Guardrails:
        - Do NOT import modules to read their docstrings
          ✅ Use ast.parse() only
        - Do NOT allow invalid enum values silently
          ✅ Emit ValidationWarning for unknown values

    Tags:
        - doc_header
        - metadata
        - model
        - dataclass
        - changelog

    Doc-Types:
        - API_REFERENCE (section: "Models", priority: 8)

    Attributes:
        summary: One-line module summary (first line of docstring).
        stability: Module stability level.
        tier: Deployment tier requirement.
        since: Version when module was introduced.
        dependencies: Dependency description string.
        doc_types: List of documentation type classifications.
        tags: List of lowercase tag identifiers.
        body: Prose body after the header block.
        raw: The complete original docstring.
    """

    summary: str
    stability: Stability = Stability.STABLE
    tier: Tier = Tier.NONE
    since: str | None = None
    dependencies: str = "stdlib-only"
    doc_types: tuple[DocType, ...] = (DocType.API_REFERENCE,)
    tags: tuple[str, ...] = ()
    body: str = ""
    raw: str = ""


@dataclass(frozen=True)
class ModuleInfo:
    """Information about a single Python module.

    Attributes:
        path: Relative path from source root (e.g., ``spine/core/cache.py``).
        module_path: Dotted module path (e.g., ``spine.core.cache``).
        header: Parsed doc header (None if no docstring).
        has_header_fields: Whether the docstring contained explicit header fields.
        docstring_length: Character count of the full docstring.
    """

    path: str
    module_path: str
    header: DocHeader | None = None
    has_header_fields: bool = False
    docstring_length: int = 0


@dataclass(frozen=True)
class SidecarContent:
    """Rich content parsed from a sidecar markdown file.

    Attributes:
        migration_guide: Migration instructions (markdown).
        examples: Code examples (markdown).
        diagrams: List of Mermaid diagram strings.
        raw: Full sidecar markdown text.
    """

    migration_guide: str = ""
    examples: str = ""
    diagrams: tuple[str, ...] = ()
    raw: str = ""


@dataclass(frozen=True)
class CommitTrailers:
    """Structured trailers parsed from a commit message.

    Attributes:
        impact: Change impact classification.
        migration: Migration requirement level.
        migration_notes: Free-text migration description.
        feature_type: Feature type classification (if any).
        architecture: Architecture pattern (if any).
        domain: Domain classification (if any).
        surfaces: Public API surfaces added/changed.
        tags: Lowercase tag identifiers.
        markers: Uppercase marker labels.
        has_sidecar: Whether a sidecar file exists for this commit.
    """

    impact: Impact = Impact.INTERNAL
    migration: Migration = Migration.NONE
    migration_notes: str = ""
    feature_type: str = ""
    architecture: str = ""
    domain: str = ""
    surfaces: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    markers: tuple[str, ...] = ()
    has_sidecar: bool = False


@dataclass(frozen=True)
class CommitFile:
    """A file touched by a commit.

    Attributes:
        path: Relative file path.
        status: Git status character (A=added, M=modified, D=deleted).
    """

    path: str
    status: str  # A, M, D, R, C


@dataclass(frozen=True)
class CommitNote:
    """Complete parsed data for a single commit.

    Attributes:
        sha: Full commit SHA.
        short_sha: 7-character short SHA.
        subject: Conventional commit subject line.
        date: Commit date string (ISO-ish).
        author: Commit author name.
        body_what: "What:" section content.
        body_why: "Why:" section content.
        trailers: Parsed trailer metadata.
        files: List of files touched.
        sidecar: Rich sidecar content (if any).
        docstrings: Dict mapping module path to docstring text.
    """

    sha: str
    short_sha: str
    subject: str
    date: str = ""
    author: str = ""
    body_what: str = ""
    body_why: str = ""
    trailers: CommitTrailers = field(default_factory=CommitTrailers)
    files: tuple[CommitFile, ...] = ()
    sidecar: SidecarContent | None = None
    docstrings: dict[str, str] = field(default_factory=dict)


@dataclass
class PhaseGroup:
    """A group of commits belonging to a named phase.

    Attributes:
        number: Phase number (1-based).
        name: Human-readable phase name.
        commits: Ordered list of commits in this phase.
    """

    number: int
    name: str
    commits: list[CommitNote] = field(default_factory=list)

    @property
    def total_files(self) -> int:
        """Total unique files across all commits in this phase."""
        seen: set[str] = set()
        for c in self.commits:
            for f in c.files:
                seen.add(f.path)
        return len(seen)


@dataclass
class ModuleIndex:
    """Aggregated index of all modules grouped by classification.

    Attributes:
        modules: All parsed module info objects.
        by_doc_type: Modules grouped by doc type.
        by_tier: Modules grouped by tier.
        by_stability: Modules grouped by stability.
    """

    modules: list[ModuleInfo] = field(default_factory=list)
    by_doc_type: dict[str, list[ModuleInfo]] = field(default_factory=dict)
    by_tier: dict[str, list[ModuleInfo]] = field(default_factory=dict)
    by_stability: dict[str, list[ModuleInfo]] = field(default_factory=dict)

    def build_indexes(self) -> None:
        """Rebuild all grouping indexes from the modules list."""
        self.by_doc_type.clear()
        self.by_tier.clear()
        self.by_stability.clear()

        for mod in self.modules:
            if mod.header is None:
                continue

            # Group by doc type
            for dt in mod.header.doc_types:
                key = dt.value
                self.by_doc_type.setdefault(key, []).append(mod)

            # Group by tier
            tier_key = mod.header.tier.value
            self.by_tier.setdefault(tier_key, []).append(mod)

            # Group by stability
            stab_key = mod.header.stability.value
            self.by_stability.setdefault(stab_key, []).append(mod)


@dataclass(frozen=True)
class ValidationWarning:
    """A warning from controlled vocabulary validation.

    Attributes:
        source: Where the warning originated (file path or commit SHA).
        field: Which field had the issue.
        value: The invalid value.
        message: Human-readable warning message.
    """

    source: str
    field: str
    value: str
    message: str
