"""
Tests for CLI utilities.
"""

from __future__ import annotations

import pytest
from dataclasses import dataclass

from spine.cli.utils import _to_dict, get_connection, make_context


@dataclass
class _Sample:
    name: str = "test"
    count: int = 0


class TestToDict:
    def test_dataclass(self):
        d = _to_dict(_Sample(name="x", count=5))
        assert d == {"name": "x", "count": 5}

    def test_dict_passthrough(self):
        d = _to_dict({"a": 1})
        assert d == {"a": 1}

    def test_pydantic(self):
        from pydantic import BaseModel

        class M(BaseModel):
            x: int = 1

        d = _to_dict(M())
        assert d == {"x": 1}

    def test_other(self):
        d = _to_dict("hello")
        assert d == {"value": "hello"}


class TestMakeContext:
    def test_creates_context(self, tmp_path):
        db = str(tmp_path / "test.db")
        ctx, conn = make_context(db)
        assert ctx.caller == "cli"
        assert ctx.dry_run is False

    def test_dry_run(self, tmp_path):
        db = str(tmp_path / "test.db")
        ctx, conn = make_context(db, dry_run=True)
        assert ctx.dry_run is True
