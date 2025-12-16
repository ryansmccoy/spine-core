#!/usr/bin/env python3
"""Multi-Dimensional Tagging — Faceted Search with Provenance Tracking.

================================================================================
WHY MULTI-DIMENSIONAL TAGGING?
================================================================================

Single-dimension tags are limiting for financial entities::

    # Flat tags lose context
    tags = ["technology", "large-cap", "S&P 500", "NASDAQ"]
    # Which are sectors?  Which are indices?  Who assigned them?

Multi-dimensional tagging adds *structure*::

    TagGroupSet({
        "sector":    TagGroup(["technology", "consumer_electronics"]),
        "market_cap": TagGroup(["large_cap"]),
        "index":     TagGroup(["sp500", "nasdaq100"]),
    })

    # Now you can:
    # - Filter by sector without accidentally matching indices
    # - Track WHO assigned each tag (LLM, manual, keyword extraction)
    # - Compare entities using Jaccard similarity PER dimension


================================================================================
ARCHITECTURE: TAG DIMENSIONS
================================================================================

::

    ┌─────────────────────────────────────────────────────────────────────────┐
    │  TagGroupSet for "Apple Inc."                                           │
    ├─────────────────────────────────────────────────────────────────────────┤
    │                                                                         │
    │  sector ─────── TagGroup(["technology", "consumer_electronics"])        │
    │                 extraction_method: LLM (gpt-4)                         │
    │                                                                         │
    │  market_cap ─── TagGroup(["large_cap"])                                 │
    │                 extraction_method: AUTOMATED (from market data)         │
    │                                                                         │
    │  index ──────── TagGroup(["sp500", "nasdaq100", "djia"])               │
    │                 extraction_method: KEYWORD (from reference data)        │
    │                                                                         │
    │  geography ──── TagGroup(["us", "california", "cupertino"])             │
    │                 extraction_method: MANUAL (analyst input)               │
    │                                                                         │
    └─────────────────────────────────────────────────────────────────────────┘

    TagDimension defines the dimension name (sector, geography, etc.)
    ExtractionMethod tracks provenance (LLM, MANUAL, KEYWORD, AUTOMATED)


================================================================================
SIMILARITY AND MATCHING
================================================================================

**Jaccard Similarity** — Compare two entities across dimensions::

    apple   = TagGroupSet(sector=["tech"], index=["sp500", "nasdaq"])
    google  = TagGroupSet(sector=["tech"], index=["sp500", "nasdaq"])
    walmart = TagGroupSet(sector=["retail"], index=["sp500"])

    similarity(apple, google)  = 1.0   (identical tags per dimension)
    similarity(apple, walmart) = 0.33  (only sp500 overlap)

**Filter Matching** — Faceted search::

    # "Show me all large-cap tech companies in the S&P 500"
    registry.match(sector="technology", market_cap="large_cap", index="sp500")


================================================================================
EXAMPLE USAGE
================================================================================

Run this example:
    python examples/01_core/19_tagging.py

See Also:
    - :mod:`spine.core.taggable` — TagGroupSet, TagGroup, TagDimension
    - :mod:`spine.core.enums` — ExtractionMethod provenance tracking
"""

from spine.core.taggable import (
    ExtractionMethod,
    TagDimension,
    TagGroup,
    TagGroupSet,
)


def main():
    print("=" * 60)
    print("Multi-Dimensional Tagging")
    print("=" * 60)

    # ── 1. Create tags for a news article ───────────────────────
    print("\n--- 1. Create TagGroupSet (news article) ---")
    article_tags = TagGroupSet.create(
        tickers=["AAPL", "MSFT"],
        sectors=["Technology"],
        event_types=["earnings", "guidance"],
    )

    # Add provenance-tracked tags (simulating LLM extraction)
    article_tags.set(
        "topics",
        ["revenue beat", "services growth"],
        method=ExtractionMethod.LLM.value,
        confidence=0.92,
        extracted_by="claude-sonnet-4",
    )

    print(f"  Dimensions: {article_tags.dimensions()}")
    print(f"  Tickers:    {article_tags.tickers}")
    print(f"  Sectors:    {article_tags.sectors}")
    print(f"  Topics:     {article_tags.topics}")
    print(f"  All flat:   {article_tags.all_tags_flat()}")

    # ── 2. Individual TagGroup operations ───────────────────────
    print("\n--- 2. TagGroup operations ---")
    tg = TagGroup(
        dimension=TagDimension.TICKERS.value,
        values=["AAPL", "GOOG"],
        extraction_method=ExtractionMethod.KEYWORD.value,
        confidence=0.85,
    )
    print(f"  Has AAPL? {tg.has('AAPL')}")
    print(f"  Has TSLA? {tg.has('TSLA')}")

    tg.add("TSLA")
    print(f"  After add: {tg.values}")

    tg.remove("GOOG")
    print(f"  After remove: {tg.values}")

    # Serialization round-trip
    d = tg.to_dict()
    restored = TagGroup.from_dict(d)
    print(f"  Round-trip OK: {restored.values == tg.values}")

    # ── 3. Similarity matching ──────────────────────────────────
    print("\n--- 3. Similarity matching ---")
    other_tags = TagGroupSet.create(
        tickers=["AAPL", "GOOG"],
        sectors=["Technology"],
        event_types=["earnings"],
        topics=["revenue beat", "cloud growth"],
    )

    similarity = article_tags.matches(other_tags)
    print(f"  Default similarity: {similarity:.3f}")

    # Weighted: prioritize tickers and sectors
    weighted_sim = article_tags.matches(
        other_tags,
        weights={"tickers": 3.0, "sectors": 2.0, "event_types": 1.0, "topics": 1.0},
    )
    print(f"  Weighted similarity: {weighted_sim:.3f}")

    # ── 4. Overlap between TagGroups ────────────────────────────
    print("\n--- 4. Jaccard overlap ---")
    group_a = TagGroup(dimension="tickers", values=["AAPL", "MSFT", "GOOG"])
    group_b = TagGroup(dimension="tickers", values=["AAPL", "GOOG", "AMZN"])
    overlap = group_a.overlaps(group_b)
    print(f"  {group_a.values} vs {group_b.values}")
    print(f"  Jaccard overlap: {overlap:.3f}")  # 2/4 = 0.5

    # ── 5. Filter matching (faceted search) ─────────────────────
    print("\n--- 5. Filter matching ---")
    matches_tech = article_tags.filter_match({
        "sectors": ["Technology"],
        "event_types": ["earnings"],
    })
    print(f"  Tech + earnings filter: {matches_tech}")

    matches_health = article_tags.filter_match({
        "sectors": ["Healthcare"],
    })
    print(f"  Healthcare filter: {matches_health}")

    # ── 6. SEC filing example ───────────────────────────────────
    print("\n--- 6. SEC filing tags ---")
    filing_tags = TagGroupSet.create(
        filing_types=["10-K"],
        risk_categories=["competition", "supply_chain", "regulatory"],
        regions=["US", "China"],
        entities=["Apple Inc."],
    )
    print(f"  Dimensions: {filing_tags.dimensions()}")
    print(f"  Risk cats:  {filing_tags.get('risk_categories')}")

    print("\n" + "=" * 60)
    print("[OK] Tagging example complete")


if __name__ == "__main__":
    main()
