#!/usr/bin/env python3
"""Versioned Content — Immutable Version History with Event-Sourcing Semantics.

================================================================================
WHY CONTENT VERSIONING?
================================================================================

Data descriptions, analysis summaries, and LLM-generated content change
over time.  Traditional approaches lose history::

    # BAD: Overwrite in place
    company.description = llm_improve(company.description)
    # What was the original?  What did the LLM change?  Can we undo it?

    # BAD: Timestamp-based "versioning"
    company.description_v2 = llm_improve(company.description)
    # How many versions will there be?  Column proliferation!

VersionedContent provides **immutable, append-only version chains**::

    vc = VersionedContent.create("Original text", ContentSource.MANUAL)
    vc.add_version("Improved text", ContentSource.LLM, model="gpt-4")
    vc.add_version("Final text", ContentSource.HUMAN_REVIEWED)

    # Full history preserved
    vc.version_count       # → 3
    vc.current.text        # → "Final text"
    vc.versions[0].text    # → "Original text" (still there)
    vc.revert_to(0)        # Non-destructive: adds version 4 = copy of version 0


================================================================================
ARCHITECTURE: VERSION CHAIN
================================================================================

::

    ┌──────────────────────────────────────────────────────────────────┐
    │  VersionedContent                                                │
    │                                                                  │
    │  versions: [                                                     │
    │    V0 ─── ContentVersion(text="Raw text", source=EDGAR_FILING)  │
    │    V1 ─── ContentVersion(text="Cleaned",  source=LLM, model=…) │
    │    V2 ─── ContentVersion(text="Reviewed", source=HUMAN_REVIEW) │
    │    V3 ─── ContentVersion(text="Raw text", source=REVERT)       │
    │  ]                                                               │
    │                                                                  │
    │  current_version: 3  (always points to latest)                  │
    │  content_hash: sha256(current.text)                             │
    │  token_estimate: ~len(current.text) // 4                        │
    └──────────────────────────────────────────────────────────────────┘

Key Properties:
    - **Immutable versions** — Once added, a version is never modified
    - **Content-hash dedup** — Detect when an "update" didn't change anything
    - **Provenance tracking** — Know if text came from EDGAR, LLM, or human
    - **Token estimation** — Budget LLM costs before sending content


================================================================================
CONTENT SOURCES (Provenance)
================================================================================

::

    ┌───────────────────┬──────────────────────────────────────────────┐
    │ ContentSource     │ Meaning                                      │
    ├───────────────────┼──────────────────────────────────────────────┤
    │ MANUAL            │ Hand-written by a human                      │
    │ EDGAR_FILING      │ Extracted from SEC EDGAR                     │
    │ LLM               │ Generated/improved by language model         │
    │ HUMAN_REVIEWED    │ LLM output verified by human                 │
    │ AUTOMATED         │ Rule-based transformation                    │
    │ REVERT            │ Reverted to a previous version               │
    └───────────────────┴──────────────────────────────────────────────┘


================================================================================
EXAMPLE USAGE
================================================================================

Run this example:
    python examples/01_core/17_versioned_content.py

See Also:
    - :mod:`spine.core.versioned_content` — VersionedContent, ContentVersion
    - ``examples/01_core/22_finance_corrections.py`` — Corrections (different use case)
"""

from spine.core.versioned_content import (
    ContentSource,
    ContentType,
    ContentVersion,
    VersionedContent,
)


def main():
    print("=" * 60)
    print("Versioned Content")
    print("=" * 60)

    # ── 1. Create original news headline ────────────────────────
    print("\n--- 1. Create versioned headline ---")
    headline = VersionedContent.create(
        content="Apple beats Q4 estimates",
        content_type=ContentType.NEWS_HEADLINE,
        context={"ticker": "AAPL", "source": "reuters"},
        created_by="wire_service",
    )
    v1 = headline.current
    print(f"  ID:      {headline.id}")
    print(f"  Type:    {headline.content_type.value}")
    print(f"  v{v1.version}: {v1.content}")
    print(f"  Hash:    {v1.content_hash[:16]}...")
    print(f"  Tokens:  ~{v1.tokens_estimate}")
    print(f"  Context: {headline.context}")

    # ── 2. Add LLM-expanded version ────────────────────────────
    print("\n--- 2. Add LLM-expanded version ---")
    v2 = headline.add_version(
        content="Apple Reports Q4 Revenue of $95B, Beating Wall Street Estimates by 3.2%",
        source=ContentSource.LLM_EXPANDED,
        created_by="claude-sonnet-4",
        improvements=["added revenue figure", "added percentage beat"],
        change_notes="Expanded with specific financial data",
        confidence=0.95,
    )
    print(f"  v{v2.version}: {v2.content}")
    print(f"  Source:       {v2.source}")
    print(f"  Created by:   {v2.created_by}")
    print(f"  Improvements: {v2.improvements}")
    print(f"  Confidence:   {v2.confidence}")
    print(f"  Supersedes:   v{v2.supersedes_version}")

    # ── 3. Add another version (editorial correction) ───────────
    print("\n--- 3. Editorial correction ---")
    v3 = headline.add_version(
        content="Apple Reports Q4 Revenue of $94.9B, Beating Estimates by 3.1%",
        source=ContentSource.CORRECTION,
        created_by="editor_jsmith",
        improvements=["corrected revenue figure", "corrected percentage"],
        change_notes="Fact-checked with earnings release",
    )
    print(f"  v{v3.version}: {v3.content}")

    # ── 4. Browse version history ───────────────────────────────
    print("\n--- 4. Version history ---")
    print(f"  Total versions: {headline.version_count}")
    print(f"  Original:       {headline.original.content}")
    print(f"  Current:        {headline.current.content}")
    print()
    for v in headline.history:
        superseded = " (superseded)" if v.is_superseded else " (current)"
        print(f"  v{v.version}: [{v.source}]{superseded}")
        print(f"         {v.content[:60]}...")

    # ── 5. Revert to v1 ────────────────────────────────────────
    print("\n--- 5. Revert to v1 ---")
    v4 = headline.revert_to(1, reverted_by="editor_jsmith")
    print(f"  v{v4.version}: {v4.content}")
    print(f"  Source:     {v4.source}")
    print(f"  Supersedes: v{v4.supersedes_version}")
    print(f"  Now {headline.version_count} versions total (revert = new version)")

    # ── 6. ContentVersion standalone ────────────────────────────
    print("\n--- 6. ContentVersion serialization ---")
    cv = ContentVersion(
        version=1,
        content="Risk factor: Supply chain disruptions...",
        source=ContentSource.ORIGINAL.value,
        created_by="sec_parser",
    )
    d = cv.to_dict()
    restored = ContentVersion.from_dict(d)
    print(f"  Round-trip OK: {restored.content == cv.content}")
    print(f"  Hash match:    {restored.content_hash == cv.content_hash}")

    # ── 7. SEC filing example ───────────────────────────────────
    print("\n--- 7. SEC risk factor versioning ---")
    risk = VersionedContent.create(
        content="We face significant competition in all areas of our business.",
        content_type=ContentType.SEC_RISK_FACTOR,
        context={"cik": "0000320193", "filing_type": "10-K", "section": "1A"},
    )
    risk.add_version(
        content="We face significant competition in all areas of our business, "
        "including from companies with substantially greater resources. "
        "Our competitors may develop superior products or services.",
        source=ContentSource.LLM_EXPANDED,
        created_by="claude-sonnet-4",
        improvements=["added competitive context", "added risk detail"],
    )
    print(f"  Original:  {risk.original.content[:50]}...")
    print(f"  Expanded:  {risk.current.content[:50]}...")
    print(f"  Versions:  {risk.version_count}")

    print("\n" + "=" * 60)
    print("[OK] Versioned content example complete")


if __name__ == "__main__":
    main()
