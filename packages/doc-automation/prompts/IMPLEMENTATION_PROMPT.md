# 🔧 IMPLEMENTATION PROMPT

**For LLM: How to build the Knowledge Graph Documentation System**

*Step-by-step guide to implementing automatic documentation generation*

---

## 🎯 Your Mission

Build a **documentation automation system** that:

1. **Scans Python code** for extended docstrings
2. **Extracts structured metadata** (Manifesto, Features, Architecture, etc.)
3. **Builds EntitySpine knowledge graph** of documentation fragments
4. **Queries graph** to assemble documents
5. **Generates multiple doc types** (MANIFESTO, FEATURES, guides, ADRs, etc.)
6. **Integrates with MkDocs** for multi-page sites

---

## 📦 Package Structure

Create in `spine-core/packages/doc-automation/`:

```
doc-automation/
├── pyproject.toml              # Package config
├── README.md                   # Package overview
├── TRACKER.md                  # ✅ Already exists
├── design/
│   ├── SELF_DOCUMENTING_CODE.md       # ✅ (to be moved here)
│   ├── KNOWLEDGE_GRAPH_DOCUMENTATION.md  # ✅ Already created
│   └── ARCHITECTURE.md                   # System architecture
├── prompts/
│   ├── LLM_DECISION_PROMPT.md        # ✅ Already exists
│   ├── CODE_ANNOTATION_PROMPT.md      # ✅ Already exists (to be updated)
│   ├── EXTENDED_ANNOTATION_PROMPT.md  # ✅ Just created
│   ├── IMPLEMENTATION_PROMPT.md       # ✅ This file
│   ├── TEMPLATE_EXTRACTION_PROMPT.md  # To be created
│   ├── VALIDATION_PROMPT.md           # To be created
│   └── DOC_CLEANUP_PROMPT.md          # ✅ Already exists
├── src/
│   └── doc_automation/
│       ├── __init__.py
│       ├── parser/                    # Docstring parsing
│       │   ├── __init__.py
│       │   ├── docstring_parser.py    # Extract sections from docstrings
│       │   ├── ast_walker.py          # Walk Python AST
│       │   └── section_extractors.py  # Per-section extraction logic
│       ├── graph/                     # Knowledge graph
│       │   ├── __init__.py
│       │   ├── builder.py             # Build graph from code
│       │   ├── schema.py              # Entity/relationship schemas
│       │   ├── queries.py             # Pre-built queries
│       │   └── integration.py         # EntitySpine integration
│       ├── renderers/                 # Document generation
│       │   ├── __init__.py
│       │   ├── base.py                # Base renderer
│       │   ├── manifesto.py           # MANIFESTO.md renderer
│       │   ├── features.py            # FEATURES.md renderer
│       │   ├── architecture.py        # ARCHITECTURE.md renderer
│       │   ├── adr.py                 # ADR renderer
│       │   ├── changelog.py           # CHANGELOG.md renderer
│       │   ├── feature_guide.py       # Feature guide renderer
│       │   └── api_reference.py       # API docs renderer
│       ├── templates/                 # Jinja2 templates
│       │   ├── MANIFESTO_template.md
│       │   ├── FEATURES_template.md
│       │   ├── ARCHITECTURE_template.md
│       │   ├── ADR_template.md
│       │   ├── CHANGELOG_template.md
│       │   ├── FEATURE_GUIDE_template.md
│       │   └── API_REFERENCE_template.md
│       ├── extractors/                # Template extraction from existing docs
│       │   ├── __init__.py
│       │   ├── template_extractor.py  # Mine structure from docs
│       │   └── example_extractor.py   # Extract reusable examples
│       ├── orchestrator.py            # Main orchestration
│       ├── cli.py                     # CLI commands
│       └── config.py                  # Configuration
├── tests/
│   ├── __init__.py
│   ├── test_parser.py
│   ├── test_graph.py
│   ├── test_renderers.py
│   └── fixtures/
│       └── sample_annotated_code.py   # Test fixtures
└── examples/
    ├── annotated_class.py             # Example annotation
    └── generated_docs/                # Example outputs
        ├── MANIFESTO.md
        ├── FEATURES.md
        └── guides/
            └── EXAMPLE_GUIDE.md
```

---

## 🏗️ Implementation Phases

### **Phase 1: Docstring Parser (Week 1-2)**

Build parser that extracts structured sections from Python docstrings.

#### Task 1.1: AST Walker

```python
# src/doc_automation/parser/ast_walker.py

import ast
from pathlib import Path
from dataclasses import dataclass
from typing import Iterator

@dataclass
class ClassInfo:
    """Information about a Python class."""
    name: str
    module: str
    file_path: Path
    line_number: int
    docstring: str | None
    methods: list['MethodInfo']
    bases: list[str]

@dataclass
class MethodInfo:
    """Information about a class method."""
    name: str
    signature: str
    docstring: str | None
    line_number: int
    is_public: bool

class ASTWalker:
    """Walk Python AST and extract class/method info."""
    
    def walk_file(self, file_path: Path) -> list[ClassInfo]:
        """Extract all classes from Python file."""
        with open(file_path) as f:
            tree = ast.parse(f.read(), filename=str(file_path))
        
        classes = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                class_info = self._extract_class(node, file_path)
                classes.append(class_info)
        
        return classes
    
    def _extract_class(self, node: ast.ClassDef, file_path: Path) -> ClassInfo:
        """Extract ClassInfo from AST node."""
        # Get docstring
        docstring = ast.get_docstring(node)
        
        # Get methods
        methods = []
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                method = self._extract_method(item)
                methods.append(method)
        
        # Get base classes
        bases = [self._get_base_name(base) for base in node.bases]
        
        return ClassInfo(
            name=node.name,
            module=self._get_module_name(file_path),
            file_path=file_path,
            line_number=node.lineno,
            docstring=docstring,
            methods=methods,
            bases=bases
        )
    
    def _extract_method(self, node: ast.FunctionDef) -> MethodInfo:
        """Extract MethodInfo from AST node."""
        # Implementation...
        pass
```

**Validation:**
```python
# tests/test_parser.py
def test_ast_walker_extracts_class():
    walker = ASTWalker()
    classes = walker.walk_file(Path("tests/fixtures/sample_class.py"))
    assert len(classes) == 1
    assert classes[0].name == "SampleClass"
    assert classes[0].docstring is not None
```

#### Task 1.2: Docstring Section Extractor

```python
# src/doc_automation/parser/docstring_parser.py

import re
from dataclasses import dataclass, field
from typing import Any

@dataclass
class DocumentationFragment:
    """A piece of documentation extracted from code."""
    
    fragment_id: str
    fragment_type: str  # manifesto | architecture | feature | etc.
    content: str
    format: str  # markdown | python | ascii_diagram | mermaid
    
    # Source
    source_file: str
    source_class: str | None
    source_method: str | None
    source_line: int | None
    
    # Tags
    tags: list[str] = field(default_factory=list)
    doc_types: list[str] = field(default_factory=list)
    sections: dict[str, str] = field(default_factory=dict)
    
    # Metadata
    priority: int = 5
    confidence: float = 1.0

class DocstringParser:
    """Parse extended docstrings into structured fragments."""
    
    # Section markers
    SECTIONS = [
        "Manifesto",
        "Architecture",
        "Features",
        "Examples",
        "Performance",
        "Guardrails",
        "Context",
        "ADR",
        "Changelog",
        "Feature-Guide",
        "Unified-Data-Model",
        "Architecture-Doc",
        "Tags",
        "Doc-Types"
    ]
    
    def parse(self, docstring: str, source_info: dict) -> list[DocumentationFragment]:
        """Parse docstring into fragments."""
        if not docstring:
            return []
        
        # Split into sections
        sections = self._split_sections(docstring)
        
        # Extract fragments
        fragments = []
        
        # Manifesto fragment
        if "Manifesto" in sections:
            frag = DocumentationFragment(
                fragment_id=self._generate_id(source_info, "manifesto"),
                fragment_type="manifesto",
                content=sections["Manifesto"],
                format="markdown",
                source_file=source_info["file"],
                source_class=source_info.get("class"),
                source_method=source_info.get("method"),
                source_line=source_info["line"],
                tags=self._extract_tags(sections),
                doc_types=self._extract_doc_types(sections),
                sections=self._extract_section_mappings(sections)
            )
            fragments.append(frag)
        
        # Architecture fragment
        if "Architecture" in sections:
            frag = DocumentationFragment(
                fragment_id=self._generate_id(source_info, "architecture"),
                fragment_type="architecture",
                content=sections["Architecture"],
                format=self._detect_format(sections["Architecture"]),
                source_file=source_info["file"],
                source_class=source_info.get("class"),
                source_line=source_info["line"],
                tags=self._extract_tags(sections),
                doc_types=self._extract_doc_types(sections)
            )
            fragments.append(frag)
        
        # Features fragment
        if "Features" in sections:
            frag = DocumentationFragment(
                fragment_id=self._generate_id(source_info, "features"),
                fragment_type="features",
                content=sections["Features"],
                format="markdown",
                source_file=source_info["file"],
                source_class=source_info.get("class"),
                source_line=source_info["line"],
                tags=self._extract_tags(sections),
                doc_types=self._extract_doc_types(sections)
            )
            fragments.append(frag)
        
        # Add more fragments for other sections...
        
        return fragments
    
    def _split_sections(self, docstring: str) -> dict[str, str]:
        """Split docstring into sections."""
        sections = {}
        current_section = None
        current_content = []
        
        for line in docstring.splitlines():
            # Check if line is a section header
            stripped = line.strip()
            if stripped.endswith(':') and stripped[:-1] in self.SECTIONS:
                # Save previous section
                if current_section:
                    sections[current_section] = '\n'.join(current_content).strip()
                
                # Start new section
                current_section = stripped[:-1]
                current_content = []
            elif current_section:
                current_content.append(line)
            else:
                # Before first section (summary/description)
                if "summary" not in sections:
                    sections["summary"] = []
                sections["summary"].append(line)
        
        # Save last section
        if current_section:
            sections[current_section] = '\n'.join(current_content).strip()
        
        # Process summary
        if "summary" in sections and isinstance(sections["summary"], list):
            sections["summary"] = '\n'.join(sections["summary"]).strip()
        
        return sections
    
    def _extract_tags(self, sections: dict[str, str]) -> list[str]:
        """Extract tags from Tags section."""
        if "Tags" not in sections:
            return []
        
        tags = []
        for line in sections["Tags"].splitlines():
            line = line.strip()
            if line.startswith('-'):
                tag = line[1:].strip()
                # Remove comments
                if '#' in tag:
                    tag = tag[:tag.index('#')].strip()
                tags.append(tag)
        
        return tags
    
    def _extract_doc_types(self, sections: dict[str, str]) -> list[str]:
        """Extract doc types from Doc-Types section."""
        if "Doc-Types" not in sections:
            return []
        
        doc_types = []
        for line in sections["Doc-Types"].splitlines():
            line = line.strip()
            if line.startswith('-'):
                # Parse: "MANIFESTO (section: "Core", priority: 10)"
                match = re.match(r'-\s*(\w+)', line)
                if match:
                    doc_types.append(match.group(1))
        
        return doc_types
    
    def _extract_section_mappings(self, sections: dict[str, str]) -> dict[str, str]:
        """Extract section mappings from Doc-Types section."""
        if "Doc-Types" not in sections:
            return {}
        
        mappings = {}
        for line in sections["Doc-Types"].splitlines():
            line = line.strip()
            if line.startswith('-'):
                # Parse: "MANIFESTO (section: "Core Principles", priority: 10)"
                match = re.match(r'-\s*(\w+)\s*\(section:\s*"([^"]+)"', line)
                if match:
                    doc_type = match.group(1)
                    section = match.group(2)
                    mappings[doc_type] = section
        
        return mappings
    
    def _detect_format(self, content: str) -> str:
        """Detect content format (markdown, python, ascii_diagram, mermaid)."""
        if "```mermaid" in content:
            return "mermaid"
        elif "```python" in content or ">>>" in content:
            return "python"
        elif self._looks_like_ascii_diagram(content):
            return "ascii_diagram"
        else:
            return "markdown"
    
    def _looks_like_ascii_diagram(self, content: str) -> bool:
        """Check if content looks like ASCII diagram."""
        # Look for box drawing characters, arrows, etc.
        indicators = ['┌', '└', '│', '─', '→', '↓', '▼', '┬', '┴']
        return any(char in content for char in indicators)
    
    def _generate_id(self, source_info: dict, fragment_type: str) -> str:
        """Generate unique fragment ID."""
        parts = [
            source_info["file"],
            source_info.get("class", "module"),
            fragment_type
        ]
        return ":".join(parts)
```

**Validation:**
```python
# tests/test_parser.py
def test_docstring_parser_extracts_manifesto():
    docstring = '''
    Summary line.
    
    Manifesto:
        This is the core principle.
        
        Another principle.
    
    Tags:
        - core_concept
        - testing
    
    Doc-Types:
        - MANIFESTO (section: "Core", priority: 10)
    '''
    
    parser = DocstringParser()
    fragments = parser.parse(docstring, {"file": "test.py", "class": "Test", "line": 1})
    
    assert len(fragments) > 0
    manifesto_frag = next(f for f in fragments if f.fragment_type == "manifesto")
    assert "core principle" in manifesto_frag.content
    assert "core_concept" in manifesto_frag.tags
    assert "MANIFESTO" in manifesto_frag.doc_types
```

---

### **Phase 2: Knowledge Graph Builder (Week 3-4)**

Build graph using EntitySpine to model doc fragments.

#### Task 2.1: Entity Schema

```python
# src/doc_automation/graph/schema.py

from entityspine import Entity, IdentifierClaim, Relationship
from dataclasses import dataclass

@dataclass
class DocFragment:
    """Documentation fragment as EntitySpine entity."""
    entity_id: str
    primary_name: str
    entity_type: str = "DOC_FRAGMENT"
    fragment_type: str = ""  # manifesto | architecture | etc.
    content: str = ""
    format: str = "markdown"
    source_file: str = ""
    source_class: str | None = None
    tags: list[str] = None
    doc_types: list[str] = None

@dataclass
class CodeClass:
    """Code class as EntitySpine entity."""
    entity_id: str
    primary_name: str
    entity_type: str = "CODE_CLASS"
    module: str = ""
    file_path: str = ""
    line_number: int = 0
```

#### Task 2.2: Graph Builder

```python
# src/doc_automation/graph/builder.py

from pathlib import Path
from entityspine import Entity, IdentifierClaim, Relationship
from ..parser.ast_walker import ASTWalker
from ..parser.docstring_parser import DocstringParser

class KnowledgeGraphBuilder:
    """Build documentation knowledge graph from code."""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.entities = {}
        self.claims = []
        self.relationships = []
        self.walker = ASTWalker()
        self.parser = DocstringParser()
    
    def build(self) -> dict:
        """Scan all Python files and build graph."""
        
        # Find all Python files
        py_files = list(self.project_root.rglob("*.py"))
        
        for py_file in py_files:
            # Skip tests, __pycache__, etc.
            if self._should_skip(py_file):
                continue
            
            self._process_file(py_file)
        
        return {
            "entities": list(self.entities.values()),
            "claims": self.claims,
            "relationships": self.relationships
        }
    
    def _should_skip(self, file_path: Path) -> bool:
        """Check if file should be skipped."""
        skip_patterns = ["test_", "__pycache__", ".pyc", "venv", ".venv"]
        return any(pattern in str(file_path) for pattern in skip_patterns)
    
    def _process_file(self, file_path: Path):
        """Extract documentation from file."""
        
        # Walk AST
        classes = self.walker.walk_file(file_path)
        
        for cls in classes:
            # Create entity for code class
            class_entity = Entity(
                primary_name=f"{cls.module}.{cls.name}",
                entity_type="CODE_CLASS",
                source_system="code_scanner",
                source_id=str(file_path)
            )
            self.entities[class_entity.entity_id] = class_entity
            
            # Parse docstring
            if cls.docstring:
                source_info = {
                    "file": str(file_path),
                    "class": cls.name,
                    "line": cls.line_number
                }
                fragments = self.parser.parse(cls.docstring, source_info)
                
                for fragment in fragments:
                    # Create entity for fragment
                    frag_entity = Entity(
                        primary_name=fragment.content[:50],  # First 50 chars as name
                        entity_type="DOC_FRAGMENT",
                        source_system="code_annotations",
                        source_id=fragment.fragment_id
                    )
                    self.entities[frag_entity.entity_id] = frag_entity
                    
                    # Link fragment to class
                    rel = Relationship(
                        from_entity_id=frag_entity.entity_id,
                        relationship_type="EXTRACTED_FROM",
                        to_entity_id=class_entity.entity_id,
                        source_system="doc_automation",
                        confidence=1.0
                    )
                    self.relationships.append(rel)
                    
                    # Add claims for doc types
                    for doc_type in fragment.doc_types:
                        claim = IdentifierClaim(
                            entity_id=frag_entity.entity_id,
                            scheme="DOC_TYPE",
                            identifier=doc_type,
                            value=fragment.sections.get(doc_type),
                            confidence=fragment.priority / 10.0
                        )
                        self.claims.append(claim)
                    
                    # Add claims for tags
                    for tag in fragment.tags:
                        claim = IdentifierClaim(
                            entity_id=frag_entity.entity_id,
                            scheme="TAG",
                            identifier=tag,
                            confidence=1.0
                        )
                        self.claims.append(claim)
```

**Validation:**
```python
# tests/test_graph.py
def test_graph_builder_creates_entities():
    builder = KnowledgeGraphBuilder(Path("tests/fixtures"))
    graph = builder.build()
    
    assert len(graph["entities"]) > 0
    assert len(graph["claims"]) > 0
    assert len(graph["relationships"]) > 0
    
    # Check entity types
    entity_types = [e.entity_type for e in graph["entities"]]
    assert "CODE_CLASS" in entity_types
    assert "DOC_FRAGMENT" in entity_types
```

---

### **Phase 3: Document Renderers (Week 5-7)**

Build renderers that query graph and generate docs.

#### Task 3.1: Base Renderer

```python
# src/doc_automation/renderers/base.py

from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from ..graph.queries import DocumentationQuery

class BaseRenderer:
    """Base class for document renderers."""
    
    def __init__(self, graph: dict, template_dir: Path):
        self.graph = graph
        self.query = DocumentationQuery(graph)
        
        # Setup Jinja2
        self.env = Environment(
            loader=FileSystemLoader(template_dir),
            trim_blocks=True,
            lstrip_blocks=True
        )
    
    def render(self) -> str:
        """Render document (override in subclass)."""
        raise NotImplementedError
    
    def _get_template(self, template_name: str):
        """Load Jinja2 template."""
        return self.env.get_template(template_name)
```

#### Task 3.2: MANIFESTO Renderer

```python
# src/doc_automation/renderers/manifesto.py

from datetime import datetime
from .base import BaseRenderer

class ManifestoRenderer(BaseRenderer):
    """Render MANIFESTO.md from graph."""
    
    def render(self) -> str:
        """Generate MANIFESTO.md content."""
        
        # Query fragments tagged for MANIFESTO
        fragments = self.query.get_fragments_for_doc_type("MANIFESTO")
        
        # Group by section
        sections = self._group_by_section(fragments)
        
        # Load template
        template = self._get_template("MANIFESTO_template.md")
        
        # Render
        content = template.render(
            sections=sections,
            generated_at=datetime.now(),
            total_fragments=len(fragments)
        )
        
        return content
    
    def _group_by_section(self, fragments: list) -> dict:
        """Group fragments by section name."""
        sections = {}
        
        for frag in fragments:
            section_name = frag.get("section", "General")
            if section_name not in sections:
                sections[section_name] = []
            sections[section_name].append(frag)
        
        # Sort by priority
        for section_name in sections:
            sections[section_name].sort(
                key=lambda f: f.get("priority", 5),
                reverse=True
            )
        
        return sections
```

**Template:**
```markdown
{# templates/MANIFESTO_template.md #}
# MANIFESTO

**Core Principles and Philosophy**

*Auto-generated from code annotations on {{ generated_at.strftime("%Y-%m-%d") }}*

---

{% for section_name, fragments in sections.items() %}
## {{ section_name }}

{% for fragment in fragments %}
{{ fragment.content }}

{% if fragment.source_class %}
*From [`{{ fragment.source_class }}`]({{ fragment.source_file }}#L{{ fragment.source_line }})*
{% endif %}

{% endfor %}
{% endfor %}

---

*{{ total_fragments }} principles extracted from codebase*
```

---

### **Phase 4: CLI & Orchestration (Week 8-9)**

Build CLI and orchestrator.

#### Task 4.1: CLI

```python
# src/doc_automation/cli.py

import click
from pathlib import Path
from .orchestrator import DocumentationOrchestrator

@click.group()
def cli():
    """Documentation automation CLI."""
    pass

@cli.command()
@click.option("--project-root", type=click.Path(exists=True), default=".")
@click.option("--output-dir", type=click.Path(), default="docs")
@click.option("--doc-type", multiple=True, help="Specific doc types to generate")
def build(project_root, output_dir, doc_type):
    """Generate documentation."""
    
    orchestrator = DocumentationOrchestrator(
        project_root=Path(project_root),
        output_dir=Path(output_dir)
    )
    
    if doc_type:
        for dt in doc_type:
            orchestrator.generate_doc_type(dt)
    else:
        orchestrator.generate_all()
    
    click.echo(f"✅ Documentation generated in {output_dir}")

@cli.command()
@click.argument("file_path", type=click.Path(exists=True))
def extract(file_path):
    """Extract documentation fragments from file."""
    # Implementation...
    pass

@cli.command()
def validate():
    """Validate annotated code."""
    # Implementation...
    pass

if __name__ == "__main__":
    cli()
```

---

## ✅ Validation & Testing

### Unit Tests

```python
# tests/test_full_pipeline.py

def test_full_pipeline():
    """Test complete pipeline: code → graph → docs."""
    
    # 1. Build graph
    builder = KnowledgeGraphBuilder(Path("tests/fixtures"))
    graph = builder.build()
    
    assert len(graph["entities"]) > 0
    
    # 2. Render MANIFESTO
    renderer = ManifestoRenderer(graph, template_dir=Path("templates"))
    content = renderer.render()
    
    assert "# MANIFESTO" in content
    assert "Core Principles" in content
    
    # 3. Write to file
    output_path = Path("tests/output/MANIFESTO.md")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content)
    
    assert output_path.exists()
```

### Integration Test

```bash
# Use real annotated code
docbuilder build --project-root tests/fixtures --output-dir tests/output

# Verify outputs
ls tests/output/
# Should show: MANIFESTO.md, FEATURES.md, GUARDRAILS.md
```

---

## 📊 Success Criteria

**Phase 1 Complete:**
- [ ] Parser extracts all sections from docstrings
- [ ] AST walker finds all classes and methods
- [ ] Unit tests pass (90%+ coverage)

**Phase 2 Complete:**
- [ ] Graph builder creates entities and relationships
- [ ] Claims added for tags and doc-types
- [ ] Can query graph for fragments

**Phase 3 Complete:**
- [ ] MANIFESTO.md renders correctly
- [ ] FEATURES.md renders correctly
- [ ] Templates support all doc types

**Phase 4 Complete:**
- [ ] CLI commands work (`build`, `extract`, `validate`)
- [ ] Full pipeline test passes
- [ ] Documentation generated matches hand-written quality

---

## 🚀 Next Steps

After core implementation:

1. **Template Extraction** - Mine structure from existing docs
2. **Advanced Renderers** - ADRs, changelogs, feature guides
3. **MkDocs Integration** - Auto-update navigation
4. **CI/CD Integration** - Pre-commit hooks, PR checks
5. **LLM Enhancement** - Use LLM to improve generated content

---

*Build it once, generate docs forever.*
