"""Documentation carrier modules for auto-generated reference docs.

This package contains Python modules whose primary purpose is to carry
structured documentation content in their docstrings. The document-spine
pipeline extracts this content and generates polished markdown files.

Why carrier modules instead of raw markdown files?
    - Version-controlled alongside code (same repo, same PR)
    - Flows through the same docspine pipeline as code annotations
    - Consistent formatting via renderers
    - Single ``docspine build --all`` generates everything
    - No scattered markdown files to maintain manually

Package Layout::

    spine/docs/
    ├── __init__.py          ← this file
    ├── principles.py        ← P001-P020 core design principles
    ├── tenets.py            ← 10 tenets (60-second manifesto)
    ├── anti_patterns.py     ← AP001-AP015 + NG001-NG007
    ├── practices.py         ← Best practices by topic
    ├── design_rationale.py  ← 15 architectural decisions
    ├── glossary.py          ← Canonical terminology
    ├── style_guide.py       ← Code style rules
    └── concepts/
        ├── __init__.py
        ├── overview.py      ← Architecture layers
        ├── error_handling.py← Result + SpineError
        ├── primitives.py    ← Operation, Step, Workflow
        ├── protocols.py     ← Protocol pattern
        ├── execution.py     ← Runs, replay, DLQ
        └── temporal.py      ← Temporal provenance

Tags: documentation, carrier, meta
Doc-Types: ARCHITECTURE (section: "Documentation Carriers", priority: 3)
"""
