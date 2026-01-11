"""Rich console singleton and helpers."""

import os
import sys

from rich.console import Console

from market_spine.app.services.tier import TierNormalizer

# Force UTF-8 encoding on Windows to avoid cp1252 issues with Unicode chars
# This is safe because VS Code and modern terminals support UTF-8
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

# Global console instance
# Use force_terminal=False to avoid legacy Windows renderer issues with Unicode
console = Console(force_terminal=False, legacy_windows=False)

# Tier normalizer singleton for CLI helpers
_tier_normalizer = TierNormalizer()


def get_tier_values() -> list[str]:
    """Get valid tier values from service layer."""
    return _tier_normalizer.get_valid_values()
