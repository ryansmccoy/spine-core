"""
Tests for spine.core.taggable models.

Moved from entityspine.domain.taggable as part of SRP refactor (2026-02-07).
These are generic multi-dimensional tagging models applicable to any content type.
"""

from spine.core.taggable import (
    ExtractionMethod,
    TagDimension,
    TaggableMixin,
    TagGroup,
    TagGroupSet,
)


class TestTagGroup:
    """TagGroup: a named dimension with values."""

    def test_create(self):
        group = TagGroup(dimension="topics", values=["python", "fastapi"])
        assert group.dimension == "topics"
        assert "python" in group.values

    def test_add_values(self):
        group = TagGroup(dimension="topics", values=["python"])
        group.add("fastapi", "django")
        assert "fastapi" in group.values
        assert "django" in group.values

    def test_remove_values(self):
        group = TagGroup(dimension="topics", values=["python", "fastapi"])
        group.remove("python")
        assert "python" not in group.values
        assert "fastapi" in group.values

    def test_has(self):
        group = TagGroup(dimension="topics", values=["python"])
        assert group.has("python")
        assert not group.has("java")

    def test_overlaps(self):
        g1 = TagGroup(dimension="topics", values=["python", "fastapi"])
        g2 = TagGroup(dimension="topics", values=["python", "django"])
        overlap = g1.overlaps(g2)
        assert 0.0 < overlap < 1.0  # partial overlap

    def test_to_dict_from_dict_roundtrip(self):
        group = TagGroup(dimension="topics", values=["python", "fastapi"], confidence=0.9)
        d = group.to_dict()
        restored = TagGroup.from_dict(d)
        assert restored.dimension == "topics"
        assert restored.values == group.values
        assert restored.confidence == 0.9


class TestTagGroupSet:
    """TagGroupSet: collection of orthogonal tag dimensions."""

    def test_create_factory(self):
        tags = TagGroupSet.create(
            topics=["python", "fastapi"],
            technologies=["docker"],
        )
        assert tags.topics == ["fastapi", "python"]  # sorted
        assert tags.technologies == ["docker"]

    def test_set_and_get(self):
        tags = TagGroupSet()
        tags.set("topics", ["python", "fastapi"])
        assert tags.get("topics") == ["fastapi", "python"]

    def test_add(self):
        tags = TagGroupSet()
        tags.add("tickers", "AAPL", "MSFT")
        assert "AAPL" in tags.tickers
        assert "MSFT" in tags.tickers

    def test_dimensions(self):
        tags = TagGroupSet.create(topics=["a"], tickers=["AAPL"])
        dims = tags.dimensions()
        assert "topics" in dims
        assert "tickers" in dims

    def test_all_tags_flat(self):
        tags = TagGroupSet.create(topics=["python"], tickers=["AAPL"])
        flat = tags.all_tags_flat()
        assert "topics:python" in flat
        assert "tickers:AAPL" in flat

    def test_matches_identical(self):
        t1 = TagGroupSet.create(topics=["python"])
        t2 = TagGroupSet.create(topics=["python"])
        assert t1.matches(t2) == 1.0

    def test_matches_partial(self):
        t1 = TagGroupSet.create(topics=["python", "fastapi"])
        t2 = TagGroupSet.create(topics=["python", "django"])
        sim = t1.matches(t2)
        assert 0.0 < sim < 1.0

    def test_filter_match(self):
        tags = TagGroupSet.create(topics=["python"], tickers=["AAPL"])
        assert tags.filter_match({"topics": ["python"]})
        assert not tags.filter_match({"topics": ["java"]})

    def test_merge_union(self):
        t1 = TagGroupSet.create(topics=["python"])
        t2 = TagGroupSet.create(topics=["fastapi"], tickers=["AAPL"])
        merged = t1.merge(t2)
        assert "python" in merged.topics
        assert "fastapi" in merged.topics
        assert "AAPL" in merged.tickers

    def test_from_flat(self):
        tags = TagGroupSet.from_flat(["python", "AAPL", "test.py", "question"])
        assert "python" in tags.technologies
        assert "AAPL" in tags.tickers
        assert "test.py" in tags.get("files")

    def test_to_dict_from_dict_roundtrip(self):
        tags = TagGroupSet.create(topics=["python"], tickers=["AAPL"])
        d = tags.to_dict()
        restored = TagGroupSet.from_dict(d)
        assert restored.topics == tags.topics
        assert restored.tickers == tags.tickers


class TestTaggableMixin:
    """TaggableMixin: adds tagging to any dataclass."""

    def test_add_tags(self):
        obj = TaggableMixin()
        obj.add_tags("topics", ["python", "fastapi"])
        assert "python" in obj.get_tags("topics")

    def test_set_tags(self):
        obj = TaggableMixin()
        obj.set_tags("intent", "question")
        assert obj.tag_groups.intent == "question"

    def test_matches_tags(self):
        a = TaggableMixin()
        a.add_tags("topics", ["python"])
        b = TaggableMixin()
        b.add_tags("topics", ["python"])
        assert a.matches_tags(b) == 1.0


class TestEnums:
    """Verify enum values."""

    def test_tag_dimensions(self):
        assert TagDimension.TOPICS.value == "topics"
        assert TagDimension.TICKERS.value == "tickers"
        assert TagDimension.FILING_TYPES.value == "filing_types"

    def test_extraction_methods(self):
        assert ExtractionMethod.LLM.value == "llm"
        assert ExtractionMethod.NER.value == "ner"
        assert ExtractionMethod.REGEX.value == "regex"
