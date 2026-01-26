"""
CLI for documentation automation.

Provides command-line interface for building knowledge graphs,
generating documentation, and validating annotations.

Usage:
    docbuilder build --all
    docbuilder build MANIFESTO.md FEATURES.md
    docbuilder validate
    docbuilder stats
"""

import json
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from doc_automation.config import DocAutomationConfig
from doc_automation.orchestrator import DocumentationOrchestrator
from doc_automation.graph.builder import KnowledgeGraphBuilder
from doc_automation.parser.ast_walker import ASTWalker
from doc_automation.parser.docstring_parser import DocstringParser

console = Console()


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """Documentation automation CLI.
    
    Generate documentation from code annotations using a knowledge graph.
    """
    pass


@cli.command()
@click.option(
    "--project-root", "-p",
    type=click.Path(exists=True),
    default=".",
    help="Root directory of the project to document.",
)
@click.option(
    "--output-dir", "-o",
    type=click.Path(),
    default="docs",
    help="Directory to write generated documentation.",
)
@click.option(
    "--doc-type", "-t",
    multiple=True,
    help="Specific doc types to generate (e.g., MANIFESTO, FEATURES). Generates all if not specified.",
)
@click.option(
    "--all", "generate_all",
    is_flag=True,
    help="Generate all documentation types.",
)
def build(project_root: str, output_dir: str, doc_type: tuple, generate_all: bool):
    """Generate documentation from code annotations.
    
    Examples:
        docbuilder build --all
        docbuilder build -t MANIFESTO -t FEATURES
        docbuilder build --project-root src --output-dir docs
    """
    console.print("\n[bold blue]📚 Documentation Automation[/bold blue]\n")
    
    orchestrator = DocumentationOrchestrator(
        project_root=Path(project_root),
        output_dir=Path(output_dir),
    )
    
    if doc_type:
        types = list(doc_type)
    elif generate_all:
        types = None  # All types
    else:
        types = None  # Default to all
    
    results = orchestrator.generate_all(doc_types=types)
    
    # Summary table
    console.print("\n[bold]Generation Summary:[/bold]")
    table = Table()
    table.add_column("Document", style="cyan")
    table.add_column("Size", justify="right")
    table.add_column("Status", justify="center")
    
    for doc_type, size in results.items():
        status = "✅" if size > 0 else "❌"
        size_str = f"{size:,} bytes" if size > 0 else "-"
        table.add_row(doc_type, size_str, status)
    
    console.print(table)


@cli.command()
@click.option(
    "--project-root", "-p",
    type=click.Path(exists=True),
    default=".",
    help="Root directory of the project.",
)
def validate(project_root: str):
    """Validate code annotations and documentation completeness.
    
    Checks that:
    - Classes have proper extended docstrings
    - Required sections are present
    - Tags and doc-types are specified
    """
    console.print("\n[bold blue]🔍 Validating Documentation[/bold blue]\n")
    
    orchestrator = DocumentationOrchestrator(
        project_root=Path(project_root),
    )
    
    result = orchestrator.validate()
    
    # Display results
    if result["valid"]:
        console.print("[bold green]✅ Validation passed![/bold green]\n")
    else:
        console.print("[bold red]❌ Validation failed![/bold red]\n")
    
    if result["issues"]:
        console.print("[bold red]Issues:[/bold red]")
        for issue in result["issues"]:
            console.print(f"  ❌ {issue}")
        console.print()
    
    if result["warnings"]:
        console.print("[bold yellow]Warnings:[/bold yellow]")
        for warning in result["warnings"]:
            console.print(f"  ⚠️  {warning}")
        console.print()
    
    # Stats
    stats = result["stats"]
    console.print("[bold]Statistics:[/bold]")
    console.print(f"  Classes found: {stats['entity_counts'].get('CODE_CLASS', 0)}")
    console.print(f"  Fragments extracted: {stats['entity_counts'].get('DOC_FRAGMENT', 0)}")
    console.print(f"  Doc types: {', '.join(stats.get('doc_types', [])) or 'none'}")
    console.print(f"  Tags: {len(stats.get('tags', []))}")


@cli.command()
@click.option(
    "--project-root", "-p",
    type=click.Path(exists=True),
    default=".",
    help="Root directory of the project.",
)
@click.option(
    "--json", "as_json",
    is_flag=True,
    help="Output as JSON.",
)
def stats(project_root: str, as_json: bool):
    """Show statistics about the knowledge graph.
    
    Displays counts of classes, fragments, tags, doc-types, etc.
    """
    orchestrator = DocumentationOrchestrator(
        project_root=Path(project_root),
    )
    
    graph_stats = orchestrator.get_stats()
    
    if as_json:
        console.print(json.dumps(graph_stats, indent=2))
    else:
        console.print("\n[bold blue]📊 Knowledge Graph Statistics[/bold blue]\n")
        
        table = Table(title="Entities")
        table.add_column("Type", style="cyan")
        table.add_column("Count", justify="right")
        
        for entity_type, count in graph_stats.get("entity_counts", {}).items():
            table.add_row(entity_type, str(count))
        
        console.print(table)
        console.print()
        
        console.print(f"[bold]Total entities:[/bold] {graph_stats.get('total_entities', 0)}")
        console.print(f"[bold]Total claims:[/bold] {graph_stats.get('total_claims', 0)}")
        console.print(f"[bold]Total relationships:[/bold] {graph_stats.get('total_relationships', 0)}")
        console.print()
        
        console.print(f"[bold]Doc types:[/bold] {', '.join(graph_stats.get('doc_types', []))}")
        console.print(f"[bold]Tags:[/bold] {', '.join(graph_stats.get('tags', [])[:10])}", end="")
        if len(graph_stats.get('tags', [])) > 10:
            console.print(f" ... and {len(graph_stats['tags']) - 10} more")
        else:
            console.print()


@cli.command()
@click.argument("file_path", type=click.Path(exists=True))
def extract(file_path: str):
    """Extract documentation fragments from a single file.
    
    Useful for testing annotation format and seeing what gets extracted.
    """
    console.print(f"\n[bold blue]📄 Extracting from {file_path}[/bold blue]\n")
    
    walker = ASTWalker()
    parser = DocstringParser()
    
    path = Path(file_path)
    classes = walker.walk_file(path)
    
    console.print(f"Found {len(classes)} classes\n")
    
    for cls in classes:
        console.print(f"[bold cyan]{cls.name}[/bold cyan]")
        console.print(f"  Module: {cls.module}")
        console.print(f"  Line: {cls.line_number}")
        console.print(f"  Has extended docstring: {'✅' if cls.has_extended_docstring else '❌'}")
        
        if cls.docstring:
            source_info = {
                "file": str(cls.file_path),
                "class": cls.name,
                "line": cls.line_number,
            }
            fragments = parser.parse(cls.docstring, source_info)
            
            console.print(f"  Fragments extracted: {len(fragments)}")
            
            for frag in fragments:
                console.print(f"    - {frag.fragment_type}: {len(frag.content)} chars")
                if frag.tags:
                    console.print(f"      Tags: {', '.join(frag.tags)}")
                if frag.doc_types:
                    console.print(f"      Doc-types: {', '.join(frag.doc_types)}")
        
        console.print()


@cli.command()
@click.option(
    "--project-root", "-p",
    type=click.Path(exists=True),
    default=".",
    help="Root directory of the project.",
)
@click.option(
    "--output", "-o",
    type=click.Path(),
    help="Output file for the graph (JSON format).",
)
def graph(project_root: str, output: str | None):
    """Build and export the knowledge graph.
    
    Exports the graph as JSON for inspection or external tools.
    """
    console.print("\n[bold blue]🔗 Building Knowledge Graph[/bold blue]\n")
    
    builder = KnowledgeGraphBuilder(Path(project_root))
    graph_data = builder.build()
    
    stats = graph_data.get("stats", {})
    console.print(f"Files scanned: {stats.get('files_scanned', 0)}")
    console.print(f"Classes found: {stats.get('classes_found', 0)}")
    console.print(f"Annotated classes: {stats.get('annotated_classes', 0)}")
    console.print(f"Fragments extracted: {stats.get('fragments_extracted', 0)}")
    
    if output:
        output_path = Path(output)
        
        # Convert to serializable format
        export_data = builder.to_dict()
        export_data["stats"] = stats
        
        with open(output_path, "w") as f:
            json.dump(export_data, f, indent=2, default=str)
        
        console.print(f"\n✅ Graph exported to {output_path}")


@cli.command()
@click.option(
    "--project-root", "-p",
    type=click.Path(exists=True),
    default=".",
    help="Root directory of the project.",
)
def analyze(project_root: str):
    """Analyze codebase for annotation status.
    
    Shows which classes have annotations and which need them.
    """
    console.print("\n[bold blue]🔬 Analyzing Codebase[/bold blue]\n")
    
    walker = ASTWalker()
    
    annotated = []
    unannotated = []
    
    for cls in walker.walk_directory(Path(project_root)):
        if cls.has_extended_docstring:
            annotated.append(cls)
        else:
            unannotated.append(cls)
    
    # Annotated classes
    console.print(f"[bold green]✅ Annotated Classes ({len(annotated)}):[/bold green]")
    for cls in sorted(annotated, key=lambda c: c.name):
        console.print(f"  {cls.name} ({cls.module})")
    
    console.print()
    
    # Unannotated classes
    console.print(f"[bold yellow]⚠️  Unannotated Classes ({len(unannotated)}):[/bold yellow]")
    for cls in sorted(unannotated, key=lambda c: c.name)[:20]:
        console.print(f"  {cls.name} ({cls.module})")
    
    if len(unannotated) > 20:
        console.print(f"  ... and {len(unannotated) - 20} more")
    
    console.print()
    
    # Summary
    total = len(annotated) + len(unannotated)
    pct = (len(annotated) / total * 100) if total > 0 else 0
    console.print(f"[bold]Coverage: {pct:.1f}% ({len(annotated)}/{total} classes)[/bold]")


def main():
    """Entry point for CLI."""
    cli()


if __name__ == "__main__":
    main()
