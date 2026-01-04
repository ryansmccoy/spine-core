"""CLI parameter parsing and merging.

This module handles the mechanics of parsing CLI arguments from multiple
sources (flags, positional args, named options) and merging them into a
single dictionary. It does NOT normalize values - that responsibility
belongs to ParameterResolver in the command layer.

Separation of Concerns:
    ParamParser (this module):     Parse & merge CLI inputs → raw dict
    ParameterResolver (app layer): Normalize & validate → canonical dict
"""

from typing import Any


class ParamParser:
    """Parse and merge CLI parameters from multiple sources.
    
    This is a stateless utility class for CLI-specific parsing.
    Does NOT apply business logic or normalization.
    """

    @staticmethod
    def parse_key_value(arg: str) -> tuple[str, str] | None:
        """Parse key=value argument."""
        if "=" not in arg:
            return None
        key, _, value = arg.partition("=")
        return (key.strip(), value.strip())

    @staticmethod
    def merge_params(
        param_flags: list[str],  # from -p key=value
        extra_args: tuple[str, ...],  # positional key=value args
        week_ending: str | None = None,  # from --week-ending
        tier: str | None = None,  # from --tier
        file_path: str | None = None,  # from --file
        **kwargs: Any,  # other options
    ) -> dict[str, Any]:
        """
        Merge parameters from all sources.
        
        Precedence (highest to lowest):
        1. Friendly CLI options (--week-ending, --tier, --file)
        2. Positional key=value arguments
        3. -p key=value flags
        
        Note: Tier normalization is handled by commands, not here.
        """
        params: dict[str, Any] = {}

        # Start with -p flags (lowest priority)
        for flag in param_flags:
            parsed = ParamParser.parse_key_value(flag)
            if parsed:
                key, value = parsed
                params[key] = value

        # Add positional key=value args (medium priority)
        for arg in extra_args:
            parsed = ParamParser.parse_key_value(arg)
            if parsed:
                key, value = parsed
                params[key] = value

        # Add friendly options (highest priority)
        if week_ending is not None:
            params["week_ending"] = week_ending
        if tier is not None:
            params["tier"] = tier
        if file_path is not None:
            params["file_path"] = file_path

        # Add any other kwargs that aren't None
        for key, value in kwargs.items():
            if value is not None:
                params[key] = value

        # Note: Tier normalization delegated to command layer
        return params
