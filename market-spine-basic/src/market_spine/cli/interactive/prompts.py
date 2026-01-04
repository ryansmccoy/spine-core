"""Pipeline parameter prompts."""

from typing import Any, Dict, Optional

import questionary
from questionary import Style

from spine.framework.registry import get_pipeline

from ..console import console, get_tier_values

# Custom style
custom_style = Style(
    [
        ("qmark", "fg:#00ff00 bold"),
        ("question", "bold"),
        ("answer", "fg:#00ff00 bold"),
        ("pointer", "fg:#00ff00 bold"),
        ("highlighted", "fg:#00ff00 bold"),
        ("selected", "fg:#00ff00"),
    ]
)


def prompt_pipeline_params(pipeline_name: str) -> Optional[Dict[str, Any]]:
    """Prompt user for pipeline parameters."""
    try:
        pipeline_cls = get_pipeline(pipeline_name)
        spec = pipeline_cls.spec

        console.print(f"\n[bold]Pipeline:[/bold] {pipeline_name}")
        if pipeline_cls.description:
            console.print(f"[dim]{pipeline_cls.description}[/dim]")
        console.print()

        params = {}

        # Prompt for each parameter
        for param in spec.params:
            # Show if required
            suffix = " [red](required)[/red]" if param.required else " [dim](optional)[/dim]"
            question = f"{param.name}{suffix}"

            # Determine prompt type based on parameter name
            if param.name == "tier":
                value = questionary.select(
                    question,
                    choices=get_tier_values(),
                    style=custom_style,
                ).ask()
            elif param.name in ("week_ending", "date", "start_date", "end_date"):
                value = questionary.text(
                    question,
                    instruction="(YYYY-MM-DD format)",
                    style=custom_style,
                ).ask()
            elif param.name == "file_path":
                value = questionary.path(
                    question,
                    style=custom_style,
                ).ask()
            else:
                # Generic text input
                default_val = str(param.default) if param.default is not None else ""
                value = questionary.text(
                    question,
                    default=default_val,
                    style=custom_style,
                ).ask()

            # Check for cancellation
            if value is None:
                return None

            # Only include non-empty values
            if value:
                params[param.name] = value
            elif param.required:
                console.print(f"[red]Required parameter '{param.name}' cannot be empty[/red]")
                return None

        return params

    except KeyError:
        console.print(f"[red]Pipeline '{pipeline_name}' not found[/red]")
        return None
