"""
Tests for the API deps module.
"""

from __future__ import annotations

import pytest

from spine.api.deps import get_settings
from spine.api.settings import SpineCoreAPISettings


class TestGetSettings:
    def test_returns_settings_instance(self):
        get_settings.cache_clear()
        s = get_settings()
        assert isinstance(s, SpineCoreAPISettings)

    def test_cached(self):
        get_settings.cache_clear()
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2
