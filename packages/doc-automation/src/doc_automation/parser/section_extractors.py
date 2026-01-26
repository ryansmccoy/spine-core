"""
Section Extractors for specialized parsing.

Provides specialized extraction logic for different section types
(e.g., extracting examples, parsing ADR references, etc.).
"""

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Example:
    """A code example extracted from docstring."""
    code: str
    language: str
    description: str = ""
    is_doctest: bool = False
    expected_output: str | None = None


@dataclass
class ADRReference:
    """Reference to an Architecture Decision Record."""
    number: int
    title: str
    file_path: str


@dataclass
class ChangelogEntry:
    """A changelog entry."""
    version: str
    description: str
    breaking: bool = False


@dataclass
class TableRow:
    """A table row with cells."""
    cells: list[str]


@dataclass
class Table:
    """A structured table extracted from docstring."""
    title: str
    headers: list[str]
    rows: list[TableRow]
    caption: str = ""


@dataclass
class BoxedDiagram:
    """An ASCII box diagram with title."""
    title: str
    content: str
    diagram_type: str = "architecture"  # architecture, flow, hierarchy, comparison


@dataclass
class ProblemSolution:
    """Problem and solution pair for documentation."""
    problem: str
    solution: str
    example: str = ""


@dataclass
class Principle:
    """A numbered design principle."""
    number: int
    title: str
    description: str
    bullets: list[str] = field(default_factory=list)


class SectionExtractor:
    """Extract structured data from docstring sections.
    
    Provides specialized parsing for sections that need more than
    just text extraction (e.g., Examples with code, ADR references,
    changelog entries).
    
    Features:
        - Extract doctest examples from Examples section
        - Parse ADR references (number, title, path)
        - Parse changelog entries with version info
        - Extract performance metrics
    
    Examples:
        >>> extractor = SectionExtractor()
        >>> examples = extractor.extract_examples('''
        ... >>> resolver = EntityResolver()
        ... >>> resolver.resolve("AAPL")
        ... 'Apple Inc.'
        ... ''')
        >>> examples[0].is_doctest
        True
    
    Tags:
        - parser
        - extraction
        - specialized
    
    Doc-Types:
        - API_REFERENCE (section: "Parser Module", priority: 6)
    """
    
    def extract_examples(self, content: str) -> list[Example]:
        """Extract code examples from content.
        
        Args:
            content: The Examples section content
            
        Returns:
            List of Example objects
        """
        examples = []
        
        # Look for doctests (>>> format)
        doctest_pattern = re.compile(
            r'>>>\s*(.+?)(?=\n>>>|\n\n|\Z)',
            re.DOTALL
        )
        
        # Look for code blocks (```python format)
        codeblock_pattern = re.compile(
            r'```(\w+)?\n(.+?)```',
            re.DOTALL
        )
        
        # Extract doctests
        for match in doctest_pattern.finditer(content):
            code_block = match.group(0)
            lines = code_block.strip().split('\n')
            
            code_lines = []
            output_lines = []
            in_output = False
            
            for line in lines:
                if line.startswith('>>> '):
                    in_output = False
                    code_lines.append(line[4:])
                elif line.startswith('...'):
                    code_lines.append(line[4:] if len(line) > 4 else '')
                elif line.strip():
                    in_output = True
                    output_lines.append(line)
            
            examples.append(Example(
                code='\n'.join(code_lines),
                language='python',
                is_doctest=True,
                expected_output='\n'.join(output_lines) if output_lines else None,
            ))
        
        # Extract code blocks
        for match in codeblock_pattern.finditer(content):
            language = match.group(1) or 'python'
            code = match.group(2).strip()
            
            examples.append(Example(
                code=code,
                language=language,
                is_doctest=False,
            ))
        
        return examples
    
    def extract_adr_references(self, content: str) -> list[ADRReference]:
        """Extract ADR references from content.
        
        Args:
            content: The ADR section content
            
        Returns:
            List of ADRReference objects
        """
        references = []
        
        # Pattern: "- 003-identifier-claims.md: Description"
        # or "003: Title of ADR"
        pattern = re.compile(
            r'-\s*(\d+)[-_]?([^:.\n]+)?(?:\.md)?:\s*(.+)',
            re.MULTILINE
        )
        
        for match in pattern.finditer(content):
            number = int(match.group(1))
            slug = match.group(2) or ""
            description = match.group(3).strip()
            
            # Build file path
            file_path = f"adrs/{number:03d}-{slug.strip()}.md" if slug else f"adrs/{number:03d}.md"
            
            references.append(ADRReference(
                number=number,
                title=description,
                file_path=file_path.replace(' ', '-').lower(),
            ))
        
        return references
    
    def extract_changelog_entries(self, content: str) -> list[ChangelogEntry]:
        """Extract changelog entries from content.
        
        Args:
            content: The Changelog section content
            
        Returns:
            List of ChangelogEntry objects
        """
        entries = []
        
        # Pattern: "- v0.3.0: Added fuzzy name matching"
        # or "v0.3.0 - Added something"
        pattern = re.compile(
            r'-?\s*v?(\d+\.\d+(?:\.\d+)?)[-:]?\s*(.+)',
            re.MULTILINE
        )
        
        for match in pattern.finditer(content):
            version = match.group(1)
            description = match.group(2).strip()
            
            # Check for breaking change indicators
            breaking = any(indicator in description.lower() 
                         for indicator in ['breaking', 'removed', 'deprecated'])
            
            entries.append(ChangelogEntry(
                version=version,
                description=description,
                breaking=breaking,
            ))
        
        return entries
    
    def extract_performance_metrics(self, content: str) -> dict[str, Any]:
        """Extract performance metrics from content.
        
        Args:
            content: The Performance section content
            
        Returns:
            Dict of metric name to value
        """
        metrics = {}
        
        # Look for patterns like "Single lookup: <1ms"
        # or "Storage: ~500MB"
        pattern = re.compile(
            r'-\s*([^:]+):\s*([<>~]?\d+(?:\.\d+)?)\s*(\w+)',
            re.MULTILINE
        )
        
        for match in pattern.finditer(content):
            name = match.group(1).strip().lower().replace(' ', '_')
            value = match.group(2)
            unit = match.group(3)
            
            metrics[name] = {
                'value': value,
                'unit': unit,
            }
        
        return metrics
    
    def extract_guardrails(self, content: str) -> list[dict[str, str]]:
        """Extract guardrails (anti-patterns and alternatives).
        
        Args:
            content: The Guardrails section content
            
        Returns:
            List of dicts with 'anti_pattern', 'why_bad', 'correct_approach'
        """
        guardrails = []
        
        current = None
        for line in content.splitlines():
            line = line.strip()
            
            # Anti-pattern line: "- Do NOT use ticker as primary key"
            if line.startswith('- Do NOT') or line.startswith('- Do not'):
                if current:
                    guardrails.append(current)
                current = {
                    'anti_pattern': line[2:].strip(),
                    'why_bad': '',
                    'correct_approach': '',
                }
            # Reason line (continuation)
            elif current and not line.startswith('✅'):
                if not current['why_bad']:
                    current['why_bad'] = line
            # Correct approach: "✅ Instead: use CIK"
            elif current and (line.startswith('✅') or 'Instead:' in line):
                approach = line.replace('✅', '').replace('Instead:', '').strip()
                current['correct_approach'] = approach
        
        if current:
            guardrails.append(current)
        
        return guardrails

    def extract_tables(self, content: str) -> list[Table]:
        """Extract markdown tables from content.
        
        Args:
            content: The section content containing tables
            
        Returns:
            List of Table objects
        """
        tables = []
        lines = content.splitlines()
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # Look for table header (| col1 | col2 | col3 |)
            if line.startswith('|') and '|' in line[1:]:
                # Get title from line before if it exists
                title = lines[i-1].strip() if i > 0 and not lines[i-1].strip().startswith('|') else ""
                
                # Parse header row
                headers = [cell.strip() for cell in line.split('|')[1:-1]]
                
                # Skip separator row (|---|---|---|)
                i += 1
                if i < len(lines) and re.match(r'\|[-:\s|]+\|', lines[i]):
                    i += 1
                
                # Parse data rows
                rows = []
                while i < len(lines) and lines[i].strip().startswith('|'):
                    cells = [cell.strip() for cell in lines[i].split('|')[1:-1]]
                    rows.append(TableRow(cells=cells))
                    i += 1
                
                tables.append(Table(
                    title=title.rstrip(':'),
                    headers=headers,
                    rows=rows,
                ))
                continue
            
            i += 1
        
        return tables
    
    def extract_boxed_diagrams(self, content: str) -> list[BoxedDiagram]:
        """Extract ASCII box diagrams with titles.
        
        Looks for patterns like:
        ```
        ┌─────────────────────────────────────────┐
        │          TITLE OF DIAGRAM               │
        ├─────────────────────────────────────────┤
        │  content...                             │
        └─────────────────────────────────────────┘
        ```
        
        Args:
            content: The section content
            
        Returns:
            List of BoxedDiagram objects
        """
        diagrams = []
        
        # Pattern for box with title row
        # Match box top, then title row, then rest
        box_pattern = re.compile(
            r'(┌[─┬]+┐)\s*\n'  # Top border
            r'\│\s*([^│\n]+?)\s*│\s*\n'  # Title row
            r'((?:[\│├┼┤└┴┘─\s\n]|[^\n])*?)'  # Content until box ends
            r'(└[─┴]+┘)',  # Bottom border
            re.MULTILINE | re.DOTALL
        )
        
        for match in box_pattern.finditer(content):
            title = match.group(2).strip()
            full_diagram = match.group(0)
            
            # Determine diagram type from title
            diagram_type = "architecture"
            title_lower = title.lower()
            if "flow" in title_lower:
                diagram_type = "flow"
            elif "hierarchy" in title_lower or "relationship" in title_lower:
                diagram_type = "hierarchy"
            elif "principle" in title_lower or "design" in title_lower:
                diagram_type = "principles"
            
            diagrams.append(BoxedDiagram(
                title=title,
                content=full_diagram,
                diagram_type=diagram_type,
            ))
        
        return diagrams
    
    def extract_principles(self, content: str) -> list[Principle]:
        """Extract numbered design principles.
        
        Looks for patterns like:
        1. PRINCIPLE NAME
           - Detail bullet 1
           - Detail bullet 2
        
        Args:
            content: The section content
            
        Returns:
            List of Principle objects
        """
        principles = []
        
        # Pattern: "1. TITLE" or "1. Title"
        pattern = re.compile(
            r'(\d+)\.\s+([A-Z][A-Z\s]+|[A-Z][a-z].+?)(?:\n|$)',
            re.MULTILINE
        )
        
        matches = list(pattern.finditer(content))
        
        for i, match in enumerate(matches):
            number = int(match.group(1))
            title = match.group(2).strip()
            
            # Get content until next principle or end
            start = match.end()
            end = matches[i+1].start() if i < len(matches) - 1 else len(content)
            section_content = content[start:end]
            
            # Extract description (non-bullet lines)
            description_lines = []
            bullets = []
            
            for line in section_content.splitlines():
                line = line.strip()
                if line.startswith('- '):
                    bullets.append(line[2:])
                elif line and not line.startswith(('│', '┌', '└', '├', '─')):
                    description_lines.append(line)
            
            principles.append(Principle(
                number=number,
                title=title,
                description=' '.join(description_lines[:3]),  # First 3 lines
                bullets=bullets,
            ))
        
        return principles
    
    def extract_problem_solution(self, content: str) -> ProblemSolution | None:
        """Extract problem and solution pair.
        
        Looks for sections like:
        ### The Problem
        ...
        ### The Solution
        ...
        
        Args:
            content: The section content
            
        Returns:
            ProblemSolution object or None
        """
        problem = ""
        solution = ""
        
        # Look for problem section
        problem_match = re.search(
            r'(?:###?\s*)?(?:The\s+)?Problem[:\s]*\n(.*?)(?=(?:###?\s*)?(?:The\s+)?Solution|$)',
            content,
            re.IGNORECASE | re.DOTALL
        )
        if problem_match:
            problem = problem_match.group(1).strip()
        
        # Look for solution section
        solution_match = re.search(
            r'(?:###?\s*)?(?:The\s+)?Solution[:\s]*\n(.*?)(?=###|$)',
            content,
            re.IGNORECASE | re.DOTALL
        )
        if solution_match:
            solution = solution_match.group(1).strip()
        
        if problem or solution:
            return ProblemSolution(problem=problem, solution=solution)
        
        return None
    
    def clean_architecture_diagram(self, content: str) -> str:
        """Clean up architecture diagram from code annotation.
        
        Removes common indentation and extra backticks that appear
        when diagrams are embedded in docstrings.
        
        Args:
            content: Raw diagram content from docstring
            
        Returns:
            Cleaned diagram ready for markdown
        """
        lines = content.splitlines()
        
        # Remove empty lines at start/end
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        
        # Find minimum indentation
        min_indent = float('inf')
        for line in lines:
            if line.strip():
                indent = len(line) - len(line.lstrip())
                min_indent = min(min_indent, indent)
        
        if min_indent == float('inf'):
            min_indent = 0
        
        # Remove common indentation
        cleaned = []
        for line in lines:
            if line.strip():
                cleaned.append(line[min_indent:])
            else:
                cleaned.append('')
        
        return '\n'.join(cleaned)
