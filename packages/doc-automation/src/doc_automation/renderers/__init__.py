"""
Renderers module for documentation generation.

Provides renderers that query the knowledge graph and generate
documentation files using Jinja2 templates.
"""

from doc_automation.renderers.base import BaseRenderer
from doc_automation.renderers.manifesto import ManifestoRenderer
from doc_automation.renderers.features import FeaturesRenderer
from doc_automation.renderers.architecture import ArchitectureRenderer
from doc_automation.renderers.guardrails import GuardrailsRenderer
from doc_automation.renderers.adr import ADRRenderer
from doc_automation.renderers.changelog import ChangelogRenderer
from doc_automation.renderers.api_reference import APIReferenceRenderer

__all__ = [
    "BaseRenderer",
    "ManifestoRenderer",
    "FeaturesRenderer",
    "ArchitectureRenderer",
    "GuardrailsRenderer",
    "ADRRenderer",
    "ChangelogRenderer",
    "APIReferenceRenderer",
]
