# doc-automation

**Automatic documentation extraction from source code annotations**

The doc-automation package scans Python source code for special annotations and generates comprehensive documentation.

## Installation

```bash
pip install doc-automation
# or from source:
pip install -e spine-core/packages/doc-automation
```

## Usage

```python
from pathlib import Path
from doc_automation.orchestrator import DocumentationOrchestrator

orchestrator = DocumentationOrchestrator(
    project_root=Path("./src"),
    output_dir=Path("./docs/generated")
)
orchestrator.generate_all()
```

## Supported Annotations

The package looks for the following annotations in docstrings:

- `@domain:` - Domain classification
- `@layer:` - Architectural layer
- `@feature:` - Feature description  
- `@guardrail:` - Design constraints
- `@decision:` - Architecture decisions

## Generated Documents

| Document | Description |
|----------|-------------|
| MANIFESTO.md | Project vision and principles |
| FEATURES.md | Feature catalog |
| ARCHITECTURE.md | Architectural overview |
| GUARDRAILS.md | Design constraints |
| API_REFERENCE.md | API documentation |
| CHANGELOG.md | Version history |

## CLI

```bash
docbuilder --project-root ./src --output-dir ./docs/generated
```
