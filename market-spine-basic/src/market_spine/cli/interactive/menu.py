"""
Interactive menu using questionary.

Design Intent:
    This module uses subprocess.run() to shell out to CLI commands intentionally.
    This approach provides process isolation and reuses the CLI's parameter parsing,
    error handling, and output formatting. The interactive menu is a "driver" for
    the CLI, not a parallel entry point to the command layer.

    Benefits:
    - Single source of truth: CLI behavior matches interactive behavior
    - No code duplication: prompts build CLI commands, not duplicate logic
    - Clean process boundaries: each operation runs in fresh process state

    Trade-offs:
    - Cannot capture/manipulate return values programmatically
    - Subprocess overhead (negligible for CLI use case)
"""


import questionary
from questionary import Style

from spine.framework.registry import list_pipelines

from ..console import console, get_tier_values
from .prompts import prompt_pipeline_params

# Custom style for questionary
custom_style = Style(
    [
        ("qmark", "fg:#00ff00 bold"),  # Question mark
        ("question", "bold"),  # Question text
        ("answer", "fg:#00ff00 bold"),  # Answer text
        ("pointer", "fg:#00ff00 bold"),  # Selected pointer
        ("highlighted", "fg:#00ff00 bold"),  # Highlighted choice
        ("selected", "fg:#00ff00"),  # Selected choice
        ("separator", "fg:#6c6c6c"),  # Separator
        ("instruction", ""),  # Instruction
        ("text", ""),  # Plain text
        ("disabled", "fg:#858585 italic"),  # Disabled choice
    ]
)


def run_interactive_menu() -> None:
    """Run the interactive menu."""
    console.print("\n[bold cyan]Market Spine - Interactive Mode[/bold cyan]\n")

    while True:
        # Main menu choices
        action = questionary.select(
            "What would you like to do?",
            choices=[
                "Run a pipeline",
                "List available pipelines",
                "Query data",
                "Verify database",
                "Database operations",
                "Health check",
                "Exit",
            ],
            style=custom_style,
        ).ask()

        if action is None or action == "Exit":
            console.print("[yellow]Goodbye![/yellow]")
            break

        try:
            if action == "Run a pipeline":
                run_pipeline_interactive()
            elif action == "List available pipelines":
                list_pipelines_interactive()
            elif action == "Query data":
                query_data_interactive()
            elif action == "Verify database":
                verify_interactive()
            elif action == "Database operations":
                database_operations_interactive()
            elif action == "Health check":
                run_health_check_interactive()
        except KeyboardInterrupt:
            console.print("\n[yellow]Cancelled[/yellow]")
            continue


def run_pipeline_interactive() -> None:
    """Interactive pipeline runner."""
    # Get all pipelines
    all_pipelines = list_pipelines()

    # Prompt for pipeline
    pipeline = questionary.autocomplete(
        "Select pipeline:",
        choices=all_pipelines,
        style=custom_style,
    ).ask()

    if not pipeline:
        return

    # Prompt for parameters
    params = prompt_pipeline_params(pipeline)

    if params is None:
        return

    # Prompt for dry run
    dry_run = questionary.confirm(
        "Dry run? (show what would execute without running)",
        default=False,
        style=custom_style,
    ).ask()

    # Build command
    cmd_parts = ["uv", "run", "spine", "run", "run", pipeline]

    for key, value in params.items():
        # Use friendly options where available
        if key == "week_ending":
            cmd_parts.extend(["--week-ending", value])
        elif key == "tier":
            cmd_parts.extend(["--tier", value])
        elif key == "file_path":
            cmd_parts.extend(["--file", value])
        else:
            cmd_parts.extend(["-p", f"{key}={value}"])

    if dry_run:
        cmd_parts.append("--dry-run")

    # Show command
    console.print(f"\n[dim]Running: {' '.join(cmd_parts)}[/dim]\n")

    # Execute
    import subprocess

    result = subprocess.run(cmd_parts)

    if result.returncode != 0:
        console.print("\n[red]Pipeline failed[/red]")

    console.print()  # Blank line


def list_pipelines_interactive() -> None:
    """Interactive pipeline lister."""
    # Prompt for filter
    filter_prefix = questionary.text(
        "Filter by prefix (leave empty for all):",
        default="",
        style=custom_style,
    ).ask()

    # Build command
    cmd_parts = ["uv", "run", "spine", "pipelines", "list"]

    if filter_prefix:
        cmd_parts.extend(["--prefix", filter_prefix])

    # Execute
    import subprocess

    subprocess.run(cmd_parts)
    console.print()


def query_data_interactive() -> None:
    """Interactive data query."""
    # Query type
    query_type = questionary.select(
        "What to query?",
        choices=["Available weeks", "Top symbols"],
        style=custom_style,
    ).ask()

    if not query_type:
        return

    if query_type == "Available weeks":
        # Prompt for tier
        tier = questionary.select(
            "Select tier:",
            choices=get_tier_values(),
            style=custom_style,
        ).ask()

        if not tier:
            return

        # Prompt for limit
        limit = questionary.text(
            "Number of weeks:",
            default="10",
            style=custom_style,
        ).ask()

        # Build command
        cmd_parts = ["uv", "run", "spine", "query", "weeks", "--tier", tier, "--limit", limit]

    else:  # Top symbols
        # Prompt for tier
        tier = questionary.select(
            "Select tier:",
            choices=get_tier_values(),
            style=custom_style,
        ).ask()

        if not tier:
            return

        # Prompt for week
        week = questionary.text(
            "Week ending (YYYY-MM-DD):",
            style=custom_style,
        ).ask()

        if not week:
            return

        # Prompt for limit
        top = questionary.text(
            "Number of symbols:",
            default="10",
            style=custom_style,
        ).ask()

        # Build command
        cmd_parts = [
            "uv",
            "run",
            "spine",
            "query",
            "symbols",
            "--week",
            week,
            "--tier",
            tier,
            "--top",
            top,
        ]

    # Execute
    import subprocess

    subprocess.run(cmd_parts)
    console.print()


def verify_interactive() -> None:
    """Interactive verification."""
    verify_type = questionary.select(
        "What to verify?",
        choices=["Table exists", "Data quality"],
        style=custom_style,
    ).ask()

    if not verify_type:
        return

    if verify_type == "Table exists":
        table_name = questionary.text(
            "Table name:",
            style=custom_style,
        ).ask()

        if not table_name:
            return

        cmd_parts = ["uv", "run", "spine", "verify", "table", table_name]

    else:  # Data quality
        tier = questionary.select(
            "Select tier:",
            choices=get_tier_values(),
            style=custom_style,
        ).ask()

        if not tier:
            return

        week = questionary.text(
            "Week ending (YYYY-MM-DD):",
            style=custom_style,
        ).ask()

        if not week:
            return

        cmd_parts = ["uv", "run", "spine", "verify", "data", "--tier", tier, "--week", week]

    # Execute
    import subprocess

    subprocess.run(cmd_parts)
    console.print()


def database_operations_interactive() -> None:
    """Interactive database operations."""
    operation = questionary.select(
        "Select operation:",
        choices=["Initialize schema", "Reset database"],
        style=custom_style,
    ).ask()

    if not operation:
        return

    if operation == "Initialize schema":
        cmd_parts = ["uv", "run", "spine", "db", "init"]
    else:  # Reset
        console.print("\n[bold red]WARNING: This will delete ALL data![/bold red]\n")
        confirm = questionary.confirm(
            "Are you ABSOLUTELY sure?",
            default=False,
            style=custom_style,
        ).ask()

        if not confirm:
            console.print("[yellow]Cancelled[/yellow]")
            return

        cmd_parts = ["uv", "run", "spine", "db", "reset", "--force"]

    # Execute
    import subprocess

    subprocess.run(cmd_parts)
    console.print()


def run_health_check_interactive() -> None:
    """Interactive health check."""
    import subprocess

    subprocess.run(["uv", "run", "spine", "doctor", "doctor"])
    console.print()
