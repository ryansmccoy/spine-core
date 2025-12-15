"""Tests for spine.core.taggable — Multi-dimensional tagging framework."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from spine.core.taggable import (
    ExtractionMethod,
    TagDimension,
    TaggableMixin,
    TagGroup,
    TagGroupSet,
)


# ── TagDimension enum ───────────────────────────────────────────────────


class TestTagDimension:
    def test_is_string_enum(self):
        assert isinstance(TagDimension.TOPICS, str)

    def test_representative_values(self):
        assert TagDimension.TOPICS.value == "topics"
        assert TagDimension.TICKERS.value == "tickers"
        assert TagDimension.FILING_TYPES.value == "filing_types"
        assert TagDimension.CUSTOM.value == "custom"


# ── ExtractionMethod enum ───────────────────────────────────────────────


class TestExtractionMethod:
    def test_values(self):
        assert ExtractionMethod.MANUAL.value == "manual"
        assert ExtractionMethod.LLM.value == "llm"
        assert ExtractionMethod.REGEX.value == "regex"
        assert ExtractionMethod.NER.value == "ner"
        assert ExtractionMethod.INHERITED.value == "inherited"


# ── TagGroup ─────────────────────────────────────────────────────────────


class TestTagGroup:
    def test_construction(self):
        g = TagGroup(dimension="topics", values=["auth", "jwt"])
        assert g.dimension == "topics"
        assert g.values == ["auth", "jwt"]

    def test_values_sorted_and_deduped(self):
        g = TagGroup(dimension="topics", values=["z", "a", "m", "a"])
        assert g.values == ["a", "m", "z"]

    def test_default_extraction_method(self):
        g = TagGroup(dimension="topics")
        assert g.extraction_method == "manual"
        assert g.confidence == 1.0

    def test_extracted_at_auto_set(self):
        g = TagGroup(dimension="topics")
        assert g.extracted_at is not None
        assert isinstance(g.extracted_at, datetime)

    def test_add_values(self):
        g = TagGroup(dimension="topics", values=["a"])
        g.add("b", "c")
        assert g.values == ["a", "b", "c"]

    def test_add_deduplicates(self):
        g = TagGroup(dimension="topics", values=["a", "b"])
        g.add("a", "c")
        assert g.values == ["a", "b", "c"]

    def test_remove_values(self):
        g = TagGroup(dimension="topics", values=["a", "b", "c"])
        g.remove("b")
        assert g.values == ["a", "c"]

    def test_remove_nonexistent_is_noop(self):
        g = TagGroup(dimension="topics", values=["a"])
        g.remove("z")
        assert g.values == ["a"]

    def test_has(self):
        g = TagGroup(dimension="topics", values=["auth", "jwt"])
        assert g.has("auth") is True
        assert g.has("oauth") is False

    def test_overlaps_identical(self):
        g1 = TagGroup(dimension="topics", values=["a", "b"])
        g2 = TagGroup(dimension="topics", values=["a", "b"])
        assert g1.overlaps(g2) == 1.0

    def test_overlaps_disjoint(self):
        g1 = TagGroup(dimension="topics", values=["a", "b"])
        g2 = TagGroup(dimension="topics", values=["c", "d"])
        assert g1.overlaps(g2) == 0.0

    def test_overlaps_partial(self):
        g1 = TagGroup(dimension="topics", values=["a", "b"])
        g2 = TagGroup(dimension="topics", values=["b", "c"])
        # Jaccard: intersection=1, union=3
        assert abs(g1.overlaps(g2) - 1 / 3) < 1e-9

    def test_overlaps_both_empty(self):
        g1 = TagGroup(dimension="topics", values=[])
        g2 = TagGroup(dimension="topics", values=[])
        assert g1.overlaps(g2) == 1.0

    def test_overlaps_one_empty(self):
        g1 = TagGroup(dimension="topics", values=["a"])
        g2 = TagGroup(dimension="topics", values=[])
        assert g1.overlaps(g2) == 0.0

    def test_to_dict_roundtrip(self):
        g = TagGroup(
            dimension="tickers",
            values=["AAPL", "MSFT"],
            extraction_method="llm",
            confidence=0.9,
            extracted_by="gpt-4",
        )
        d = g.to_dict()
        g2 = TagGroup.from_dict(d)
        assert g2.dimension == "tickers"
        assert g2.values == ["AAPL", "MSFT"]
        assert g2.extraction_method == "llm"
        assert g2.confidence == 0.9
        assert g2.extracted_by == "gpt-4"


# ── TagGroupSet ──────────────────────────────────────────────────────────


class TestTagGroupSet:
    def test_create_factory(self):
        tags = TagGroupSet.create(
            tickers=["AAPL", "MSFT"],
            sectors=["Technology"],
        )
        assert tags.tickers == ["AAPL", "MSFT"]
        assert tags.sectors == ["Technology"]

    def test_create_with_single_string(self):
        tags = TagGroupSet.create(intent="bug-fix")
        assert tags.intent == "bug-fix"

    def test_set_dimension(self):
        tags = TagGroupSet()
        tags.set("topics", ["auth", "jwt"])
        assert tags.get("topics") == ["auth", "jwt"]

    def test_set_replaces_existing(self):
        tags = TagGroupSet()
        tags.set("topics", ["old"])
        tags.set("topics", ["new"])
        assert tags.get("topics") == ["new"]

    def test_add_creates_new(self):
        tags = TagGroupSet()
        tags.add("topics", "auth")
        assert tags.get("topics") == ["auth"]

    def test_add_appends_to_existing(self):
        tags = TagGroupSet()
        tags.add("topics", "a")
        tags.add("topics", "b")
        assert tags.get("topics") == ["a", "b"]

    def test_get_missing_dimension(self):
        tags = TagGroupSet()
        assert tags.get("nonexistent") == []

    def test_has_dimension(self):
        tags = TagGroupSet.create(tickers=["AAPL"])
        assert tags.has_dimension("tickers") is True
        assert tags.has_dimension("sectors") is False

    def test_dimensions_list(self):
        tags = TagGroupSet.create(tickers=["AAPL"], sectors=["Tech"])
        dims = tags.dimensions()
        assert "tickers" in dims
        assert "sectors" in dims

    def test_all_tags_flat(self):
        tags = TagGroupSet.create(tickers=["AAPL"], topics=["earnings"])
        flat = tags.all_tags_flat()
        assert "tickers:AAPL" in flat
        assert "topics:earnings" in flat

    def test_convenience_properties(self):
        tags = TagGroupSet.create(
            topics=["auth"],
            technologies=["fastapi"],
            projects=["spine"],
            entities=["Acme"],
            tickers=["TSLA"],
            sectors=["Auto"],
            event_types=["recall"],
        )
        assert tags.topics == ["auth"]
        assert tags.technologies == ["fastapi"]
        assert tags.projects == ["spine"]
        assert tags.entities == ["Acme"]
        assert tags.tickers == ["TSLA"]
        assert tags.sectors == ["Auto"]
        assert tags.event_types == ["recall"]

    def test_single_value_properties(self):
        tags = TagGroupSet.create(
            intent="bug-fix",
            status="resolved",
            priority="high",
        )
        assert tags.intent == "bug-fix"
        assert tags.status == "resolved"
        assert tags.priority == "high"

    def test_single_value_none_when_missing(self):
        tags = TagGroupSet()
        assert tags.intent is None
        assert tags.status is None
        assert tags.priority is None


# ── TagGroupSet.matches ──────────────────────────────────────────────────


class TestTagGroupSetMatches:
    def test_identical_sets(self):
        t1 = TagGroupSet.create(topics=["a", "b"])
        t2 = TagGroupSet.create(topics=["a", "b"])
        assert t1.matches(t2) == 1.0

    def test_both_empty(self):
        t1 = TagGroupSet()
        t2 = TagGroupSet()
        assert t1.matches(t2) == 1.0

    def test_disjoint_dimensions(self):
        t1 = TagGroupSet.create(topics=["a"])
        t2 = TagGroupSet.create(tickers=["AAPL"])
        # Both dimensions are unshared: each gets 0.0
        assert t1.matches(t2) == 0.0

    def test_partial_overlap(self):
        t1 = TagGroupSet.create(topics=["a", "b"])
        t2 = TagGroupSet.create(topics=["b", "c"])
        score = t1.matches(t2)
        assert 0.0 < score < 1.0

    def test_weighted_matching(self):
        t1 = TagGroupSet.create(topics=["a"], tickers=["AAPL"])
        t2 = TagGroupSet.create(topics=["a"], tickers=["MSFT"])
        # Heavy weight on topics → higher match
        score_heavy_topics = t1.matches(t2, weights={"topics": 10.0, "tickers": 1.0})
        score_heavy_tickers = t1.matches(t2, weights={"topics": 1.0, "tickers": 10.0})
        assert score_heavy_topics > score_heavy_tickers


# ── TagGroupSet.filter_match ─────────────────────────────────────────────


class TestFilterMatch:
    def test_match_all_present(self):
        tags = TagGroupSet.create(tickers=["AAPL", "MSFT"], sectors=["Tech"])
        assert tags.filter_match({"tickers": ["AAPL"], "sectors": ["Tech"]}) is True

    def test_no_match_missing_dimension(self):
        tags = TagGroupSet.create(tickers=["AAPL"])
        assert tags.filter_match({"sectors": ["Tech"]}) is False

    def test_no_match_wrong_value(self):
        tags = TagGroupSet.create(tickers=["AAPL"])
        assert tags.filter_match({"tickers": ["MSFT"]}) is False

    def test_empty_filter_matches_all(self):
        tags = TagGroupSet.create(tickers=["AAPL"])
        assert tags.filter_match({}) is True


# ── TagGroupSet.merge ────────────────────────────────────────────────────


class TestMerge:
    def test_union_strategy(self):
        t1 = TagGroupSet.create(topics=["a"])
        t2 = TagGroupSet.create(topics=["b"])
        merged = t1.merge(t2, conflict_strategy="union")
        assert sorted(merged.get("topics")) == ["a", "b"]

    def test_replace_strategy(self):
        t1 = TagGroupSet.create(topics=["a"])
        t2 = TagGroupSet.create(topics=["b"])
        merged = t1.merge(t2, conflict_strategy="replace")
        assert merged.get("topics") == ["b"]

    def test_keep_strategy(self):
        t1 = TagGroupSet.create(topics=["a"])
        t2 = TagGroupSet.create(topics=["b"])
        merged = t1.merge(t2, conflict_strategy="keep")
        assert merged.get("topics") == ["a"]

    def test_non_overlapping_dimensions(self):
        t1 = TagGroupSet.create(topics=["a"])
        t2 = TagGroupSet.create(tickers=["AAPL"])
        merged = t1.merge(t2)
        assert merged.get("topics") == ["a"]
        assert merged.get("tickers") == ["AAPL"]

    def test_merge_does_not_mutate_originals(self):
        t1 = TagGroupSet.create(topics=["a"])
        t2 = TagGroupSet.create(topics=["b"])
        t1.merge(t2)
        assert t1.get("topics") == ["a"]
        assert t2.get("topics") == ["b"]


# ── TagGroupSet.from_flat ────────────────────────────────────────────────


class TestFromFlat:
    def test_tickers_uppercase(self):
        tags = TagGroupSet.from_flat(["AAPL", "MSFT"])
        assert tags.tickers == ["AAPL", "MSFT"]

    def test_files_by_extension(self):
        tags = TagGroupSet.from_flat(["api.py", "index.ts"])
        assert "api.py" in tags.get("files")
        assert "index.ts" in tags.get("files")

    def test_technologies_by_keyword(self):
        tags = TagGroupSet.from_flat(["python", "docker"])
        assert tags.technologies == ["docker", "python"]

    def test_intent_keywords(self):
        tags = TagGroupSet.from_flat(["bug-fix"])
        assert tags.intent == "bug-fix"

    def test_status_keywords(self):
        tags = TagGroupSet.from_flat(["resolved"])
        assert tags.status == "resolved"

    def test_default_to_topics(self):
        tags = TagGroupSet.from_flat(["my-custom-tag"])
        assert "my-custom-tag" in tags.topics


# ── TagGroupSet serialization ────────────────────────────────────────────


class TestTagGroupSetSerialization:
    def test_to_dict_roundtrip(self):
        tags = TagGroupSet.create(
            tickers=["AAPL", "MSFT"],
            topics=["earnings"],
        )
        d = tags.to_dict()
        restored = TagGroupSet.from_dict(d)
        assert restored.tickers == ["AAPL", "MSFT"]
        assert restored.topics == ["earnings"]

    def test_repr(self):
        tags = TagGroupSet.create(topics=["a", "b"])
        r = repr(tags)
        assert "TagGroupSet" in r
        assert "topics=2" in r


# ── TaggableMixin ────────────────────────────────────────────────────────


class TestTaggableMixin:
    def test_add_tags(self):
        @dataclass
        class Article(TaggableMixin):
            title: str = ""

        article = Article(title="Test")
        article.add_tags("tickers", ["AAPL", "MSFT"])
        assert article.get_tags("tickers") == ["AAPL", "MSFT"]

    def test_add_tags_single_string(self):
        @dataclass
        class Article(TaggableMixin):
            title: str = ""

        article = Article(title="Test")
        article.add_tags("intent", "bug-fix")
        assert article.get_tags("intent") == ["bug-fix"]

    def test_set_tags_replaces(self):
        @dataclass
        class Article(TaggableMixin):
            title: str = ""

        article = Article(title="Test")
        article.add_tags("topics", ["old"])
        article.set_tags("topics", ["new"])
        assert article.get_tags("topics") == ["new"]

    def test_matches_tags(self):
        @dataclass
        class Article(TaggableMixin):
            title: str = ""

        a1 = Article(title="A")
        a1.add_tags("topics", ["auth", "jwt"])

        a2 = Article(title="B")
        a2.add_tags("topics", ["auth", "oauth"])

        score = a1.matches_tags(a2)
        assert 0.0 < score < 1.0

    def test_default_tag_groups(self):
        @dataclass
        class Article(TaggableMixin):
            title: str = ""

        article = Article(title="Test")
        assert isinstance(article.tag_groups, TagGroupSet)
        assert article.tag_groups.dimensions() == []
