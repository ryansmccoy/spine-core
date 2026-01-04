# src/market_spine/domains/otc/parser.py

"""
FINRA file parsing - shared across all tiers.

Copy this file directly to each project.
"""

import csv
from datetime import datetime
from pathlib import Path
from typing import Iterator

from market_spine.domains.otc.models import RawRecord


def parse_finra_file(file_path: Path) -> Iterator[RawRecord]:
    """
    Parse a FINRA OTC weekly transparency file.

    Expects pipe-delimited CSV with headers:
    - tierDescription
    - issueSymbolIdentifier
    - issueName
    - marketParticipantName
    - MPID
    - totalWeeklyShareQuantity
    - totalWeeklyTradeCount
    - lastUpdateDate

    Yields RawRecord for each valid row.
    """
    with open(file_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="|")

        for row in reader:
            try:
                yield RawRecord(
                    tier=row["tierDescription"],
                    symbol=row["issueSymbolIdentifier"].upper().strip(),
                    issue_name=row["issueName"],
                    venue_name=row["marketParticipantName"],
                    mpid=row["MPID"].upper().strip(),
                    share_volume=int(row["totalWeeklyShareQuantity"]),
                    trade_count=int(row["totalWeeklyTradeCount"]),
                    week_ending=datetime.strptime(row["lastUpdateDate"], "%Y-%m-%d").date(),
                )
            except (ValueError, KeyError, TypeError, AttributeError):
                continue  # Skip malformed rows


def parse_finra_content(content: str) -> Iterator[RawRecord]:
    """Parse FINRA data from string content (for HTTP downloads)."""
    import io

    reader = csv.DictReader(io.StringIO(content), delimiter="|")

    for row in reader:
        try:
            yield RawRecord(
                tier=row["tierDescription"],
                symbol=row["issueSymbolIdentifier"].upper().strip(),
                issue_name=row["issueName"],
                venue_name=row["marketParticipantName"],
                mpid=row["MPID"].upper().strip(),
                share_volume=int(row["totalWeeklyShareQuantity"]),
                trade_count=int(row["totalWeeklyTradeCount"]),
                week_ending=datetime.strptime(row["lastUpdateDate"], "%Y-%m-%d").date(),
            )
        except (ValueError, KeyError, TypeError, AttributeError):
            continue
