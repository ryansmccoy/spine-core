# src/market_spine/domains/otc/quality.py

"""Quality checks - Intermediate tier adds this."""

from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum

from market_spine.domains.otc.repository import OTCRepository


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class QualityIssue:
    code: str
    message: str
    severity: Severity


@dataclass
class QualityResult:
    week_ending: date
    issues: list[QualityIssue]
    grade: str  # A, B, C, D, F
    score: float  # 0-100


class OTCQualityChecker:
    """
    Run quality checks on OTC data.

    Basic tier has no quality checks.
    Intermediate adds: volume validation, venue coverage.
    """

    def __init__(self, repository: OTCRepository | None = None):
        self.repo = repository or OTCRepository()

    def check_week(self, week_ending: date) -> QualityResult:
        """Run all checks for a week."""
        issues = []

        current = self.repo.get_week_stats(week_ending)
        prior = self.repo.get_week_stats(week_ending - timedelta(days=7))

        # Check 1: Has any data
        if current["total_volume"] == 0:
            issues.append(
                QualityIssue(
                    code="NO_DATA",
                    message="No volume data for week",
                    severity=Severity.ERROR,
                )
            )

        # Check 2: Venue count drop
        if prior and prior["venue_count"] > 0:
            drop = (prior["venue_count"] - current["venue_count"]) / prior["venue_count"]
            if drop > 0.2:  # 20% drop
                issues.append(
                    QualityIssue(
                        code="VENUE_DROP",
                        message=f"Venue count dropped {drop:.0%}",
                        severity=Severity.WARNING,
                    )
                )

        # Check 3: Volume swing
        if prior and prior["total_volume"] > 0:
            change = abs(current["total_volume"] - prior["total_volume"]) / prior["total_volume"]
            if change > 0.5:  # 50% swing
                issues.append(
                    QualityIssue(
                        code="VOLUME_SWING",
                        message=f"Volume changed {change:.0%}",
                        severity=Severity.WARNING,
                    )
                )

        # Compute grade
        errors = sum(1 for i in issues if i.severity == Severity.ERROR)
        warnings = sum(1 for i in issues if i.severity == Severity.WARNING)

        if errors > 0:
            grade, score = "F", 0.0
        elif warnings == 0:
            grade, score = "A", 100.0
        elif warnings <= 2:
            grade, score = "B", 80.0
        else:
            grade, score = "C", 60.0

        return QualityResult(
            week_ending=week_ending,
            issues=issues,
            grade=grade,
            score=score,
        )
