"""
Tests for spine.core.versioned_content models.

Moved from entityspine.domain.versioned_content as part of SRP refactor (2026-02-07).
These are generic content versioning models (like Google Docs version history)
applicable to any content type.
"""

import pytest
from spine.core.versioned_content import (
    ContentSource,
    ContentType,
    ContentVersion,
    VersionedContent,
)


class TestContentVersion:
    """ContentVersion: a single snapshot of content."""

    def test_create(self):
        v = ContentVersion(version=1, content="Hello world", source="original")
        assert v.version == 1
        assert v.content == "Hello world"
        assert v.content_hash != ""  # auto-computed
        assert v.char_count == 11
        assert v.tokens_estimate is not None

    def test_is_original(self):
        v = ContentVersion(version=1, content="test", source="original")
        assert v.is_original
        v2 = ContentVersion(version=2, content="test v2", source="manual")
        assert not v2.is_original

    def test_to_dict_from_dict_roundtrip(self):
        v = ContentVersion(version=1, content="test", source="original", confidence=0.9)
        d = v.to_dict()
        restored = ContentVersion.from_dict(d)
        assert restored.version == 1
        assert restored.content == "test"
        assert restored.confidence == 0.9
        assert restored.content_hash == v.content_hash


class TestVersionedContent:
    """VersionedContent: content with immutable version history."""

    def test_create(self):
        vc = VersionedContent.create(
            content="Initial content",
            content_type=ContentType.TEXT,
        )
        assert vc.content == "Initial content"
        assert vc.version_count == 1
        assert vc.current.is_original

    def test_add_version(self):
        vc = VersionedContent.create(content="v1", content_type=ContentType.TEXT)
        v2 = vc.add_version(content="v2", source=ContentSource.MANUAL_EDIT, change_notes="Updated")
        assert vc.version_count == 2
        assert vc.content == "v2"
        assert v2.version == 2
        assert v2.change_notes == "Updated"

    def test_version_history(self):
        vc = VersionedContent.create(content="v1", content_type=ContentType.TEXT)
        vc.add_version(content="v2", source=ContentSource.LLM_IMPROVED)
        vc.add_version(content="v3", source=ContentSource.MANUAL_EDIT)
        assert vc.version_count == 3
        assert vc.original.content == "v1"
        assert vc.current.content == "v3"

    def test_revert_to(self):
        vc = VersionedContent.create(content="original", content_type=ContentType.TEXT)
        vc.add_version(content="modified", source=ContentSource.MANUAL_EDIT)
        reverted = vc.revert_to(1)
        assert vc.content == "original"
        assert vc.version_count == 3  # revert creates a new version

    def test_get_version(self):
        vc = VersionedContent.create(content="v1", content_type=ContentType.TEXT)
        vc.add_version(content="v2", source=ContentSource.MANUAL_EDIT)
        v1 = vc.get_version(1)
        assert v1.content == "v1"
        assert vc.get_version(99) is None

    def test_diff_versions(self):
        vc = VersionedContent.create(content="short", content_type=ContentType.TEXT)
        vc.add_version(content="this is much longer content", source=ContentSource.LLM_EXPANDED)
        diff = vc.diff_versions(1, 2)
        assert diff["char_diff"] > 0
        assert diff["from_version"] == 1
        assert diff["to_version"] == 2

    def test_to_dict_from_dict_roundtrip(self):
        vc = VersionedContent.create(content="test", content_type=ContentType.TEXT)
        vc.add_version(content="test v2", source=ContentSource.MANUAL_EDIT)
        d = vc.to_dict()
        restored = VersionedContent.from_dict(d)
        assert restored.version_count == 2
        assert restored.content == "test v2"


class TestContentEnums:
    """Verify content enum values."""

    def test_content_types(self):
        assert ContentType.CHAT_MESSAGE.value == "chat_message"
        assert ContentType.NEWS_HEADLINE.value == "news_headline"
        assert ContentType.SEC_FILING_SECTION.value == "sec_filing_section"
        assert ContentType.LLM_PROMPT.value == "llm_prompt"

    def test_content_sources(self):
        assert ContentSource.ORIGINAL.value == "original"
        assert ContentSource.LLM_IMPROVED.value == "llm_improved"
        assert ContentSource.REVERTED.value == "reverted"
