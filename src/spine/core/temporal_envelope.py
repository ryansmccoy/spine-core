"""
Temporal envelope primitives for multi-timestamp data pipelines.

Provides explicit 4-timestamp semantics so that every record in the
ecosystem carries unambiguous temporal context.  Without these, each
project invents its own ad-hoc combination of ``created_at``,
``as_of``, ``captured_at``, etc., leading to PIT query bugs.

Why This Matters — Financial Pipelines:
    In financial data, the same observation (e.g. Apple's Q3 EPS of $1.52)
    may be *announced* on one date (event_time), *published* by a vendor
    like Bloomberg or FactSet minutes later (publish_time), *ingested*
    by our pipeline hours later (ingest_time), and *effective* for a
    reporting period that started months earlier (effective_time).

    Without separating these four timestamps, common bugs arise:

    - **Look-ahead bias**: backtest uses data before it was actually known.
    - **Stale-data masking**: a correction arrives but the old version
      is still served because ``created_at`` was not disambiguated.
    - **Source-vendor confusion**: Bloomberg may publish a figure before
      FactSet — treating them identically introduces subtle timing errors
      in multi-source reconciliation (see feedspine estimates-vs-actuals).

Why This Matters — General Pipelines:
    Any event-driven or streaming architecture benefits from explicit
    temporal semantics.  CDC feeds, IoT telemetry, log aggregation,
    and workflow orchestration all face the "when did X happen vs.
    when did we learn about X" problem.  TemporalEnvelope makes this
    distinction first-class, enabling replay, backfill, and PIT queries
    without per-project ad-hoc timestamp conventions.

Key Concepts:
    TemporalEnvelope: Wraps any payload with four timestamps that answer
        distinct questions:
        - **event_time** — When did the real-world event happen?
        - **publish_time** — When did the source make it available?
        - **ingest_time** — When did *we* first capture it?
        - **effective_time** — When should downstream consumers treat it
          as valid?  (often == event_time but can differ for corrections)

    BiTemporalRecord: Adds ``valid_from / valid_to`` (business axis) and
        ``system_from / system_to`` (system/bookkeeping axis) so that
        fact tables support fully bi-temporal queries.

Related Modules:
    - :mod:`spine.core.watermarks` — cursor tracking ("how far have I read?")
    - :mod:`spine.core.backfill` — gap-fill planning when watermarks detect holes
    - :mod:`spine.core.finance.corrections` — records *why* a value changed
    - :mod:`spine.core.finance.adjustments` — corporate-action math (splits, etc.)

Example:
    >>> from spine.core.temporal_envelope import TemporalEnvelope
    >>> from spine.core.timestamps import utc_now
    >>> env = TemporalEnvelope(
    ...     event_time=utc_now(),
    ...     publish_time=utc_now(),
    ...     ingest_time=utc_now(),
    ...     payload={"symbol": "AAPL", "price": 195.0},
    ... )
    >>> env.effective_time == env.event_time  # defaults to event_time
    True

STDLIB ONLY — no Pydantic.

Tags:
    temporal, bi-temporal, envelope, PIT, pipeline, spine-core,
    financial-data, event-sourcing, replay
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Generic, TypeVar

T = TypeVar("T")


# ---------------------------------------------------------------------------
# TemporalEnvelope
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TemporalEnvelope(Generic[T]):
    """Wrap any payload with explicit 4-timestamp semantics.

    Attributes:
        event_time: When the real-world event occurred.
        publish_time: When the upstream source published / released the data.
        ingest_time: When this system first captured the data.
        payload: The domain object being wrapped.
        effective_time: When downstream consumers should treat this as valid.
            Defaults to *event_time* if not supplied.
        envelope_id: Optional unique identifier for this envelope instance.

    Examples:
        >>> from datetime import UTC, datetime
        >>> t = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
        >>> env = TemporalEnvelope(
        ...     event_time=t, publish_time=t, ingest_time=t,
        ...     payload={"ticker": "AAPL"},
        ... )
        >>> env.effective_time == t
        True
    """

    event_time: datetime
    publish_time: datetime
    ingest_time: datetime
    payload: T
    effective_time: datetime | None = None
    envelope_id: str | None = None

    def __post_init__(self) -> None:
        # Default effective_time to event_time when not explicitly set.
        if self.effective_time is None:
            object.__setattr__(self, "effective_time", self.event_time)

    # -- query helpers -------------------------------------------------------

    def known_as_of(self, cutoff: datetime) -> bool:
        """Was this envelope ingested on or before *cutoff*?

        Useful for PIT queries: "What did we know as-of date X?"
        """
        return self.ingest_time <= cutoff

    def effective_as_of(self, cutoff: datetime) -> bool:
        """Is this envelope effective on or before *cutoff*?

        Filters by the business-validity axis rather than system knowledge.
        """
        assert self.effective_time is not None  # guaranteed by __post_init__
        return self.effective_time <= cutoff

    def published_as_of(self, cutoff: datetime) -> bool:
        """Was this envelope published on or before *cutoff*?"""
        return self.publish_time <= cutoff

    # -- serialisation helpers -----------------------------------------------

    def timestamps_dict(self) -> dict[str, str | None]:
        """Return the 4 timestamps as ISO-8601 strings (for JSON/DB)."""
        return {
            "event_time": self.event_time.isoformat(),
            "publish_time": self.publish_time.isoformat(),
            "ingest_time": self.ingest_time.isoformat(),
            "effective_time": (
                self.effective_time.isoformat()
                if self.effective_time
                else None
            ),
        }

    @staticmethod
    def now_envelope(payload: T, *, event_time: datetime | None = None) -> TemporalEnvelope[T]:
        """Convenience factory: ingest_time=now, publish_time=now.

        Args:
            payload: The domain object to wrap.
            event_time: When the real-world event happened.  Defaults to now.

        Returns:
            A :class:`TemporalEnvelope` stamped with the current UTC time.
        """
        now = datetime.now(UTC)
        return TemporalEnvelope(
            event_time=event_time or now,
            publish_time=now,
            ingest_time=now,
            payload=payload,
        )


# ---------------------------------------------------------------------------
# BiTemporalRecord
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BiTemporalRecord:
    """Bi-temporal fact record for auditable, point-in-time-correct storage.

    Two independent time axes:
    - **Valid axis** (``valid_from`` / ``valid_to``): business reality
      — when was this fact true in the real world?
    - **System axis** (``system_from`` / ``system_to``): bookkeeping
      — when did our system record this version?

    ``valid_to is None`` means "currently valid".
    ``system_to is None`` means "latest system version".

    Attributes:
        record_id: Globally unique record identifier.
        entity_key: The logical entity this fact describes (e.g. ``"AAPL"``).
        valid_from: Start of business-validity period (inclusive).
        valid_to: End of business-validity period (exclusive, or ``None``).
        system_from: When this system version was created.
        system_to: When this system version was superseded (or ``None``).
        payload: Arbitrary JSON-serialisable dict with the fact data.
        provenance: Free-text origin tag (e.g. ``"sec_edgar"``, ``"manual"``).
    """

    record_id: str
    entity_key: str
    valid_from: datetime
    valid_to: datetime | None
    system_from: datetime
    system_to: datetime | None
    payload: dict[str, Any] = field(default_factory=dict)
    provenance: str = ""

    # -- query helpers -------------------------------------------------------

    @property
    def is_current(self) -> bool:
        """True if this is the latest system version and still valid."""
        return self.system_to is None and self.valid_to is None

    def valid_at(self, when: datetime) -> bool:
        """Was this fact valid in the business world at *when*?"""
        if when < self.valid_from:
            return False
        if self.valid_to is not None and when >= self.valid_to:
            return False
        return True

    def known_at(self, when: datetime) -> bool:
        """Was this system version the active record at *when*?"""
        if when < self.system_from:
            return False
        if self.system_to is not None and when >= self.system_to:
            return False
        return True

    def as_of(self, valid_when: datetime, system_when: datetime) -> bool:
        """Full bi-temporal query: was this fact valid *and* known?

        Returns True iff the fact was true in the real world at
        *valid_when* **and** our system had this version recorded at
        *system_when*.
        """
        return self.valid_at(valid_when) and self.known_at(system_when)

    def supersede(
        self,
        *,
        new_record_id: str,
        new_payload: dict[str, Any],
        correction_time: datetime | None = None,
        new_valid_from: datetime | None = None,
        new_valid_to: datetime | None = None,
        provenance: str = "",
    ) -> tuple[BiTemporalRecord, BiTemporalRecord]:
        """Create a corrected version of this record.

        Returns ``(closed_old, new_version)`` where ``closed_old`` is a copy
        of ``self`` with ``system_to`` set, and ``new_version`` carries the
        updated payload.

        Args:
            new_record_id: Unique ID for the replacement record.
            new_payload: Updated fact data.
            correction_time: When the correction was made (defaults to now).
            new_valid_from: Override the valid-from if the correction changes
                the business-validity start.  Default: keep ``self.valid_from``.
            new_valid_to: Override valid-to.  Default: keep ``self.valid_to``.
            provenance: Origin tag for the new record.

        Returns:
            Tuple of (closed old record, new record).
        """
        now = correction_time or datetime.now(UTC)
        closed = BiTemporalRecord(
            record_id=self.record_id,
            entity_key=self.entity_key,
            valid_from=self.valid_from,
            valid_to=self.valid_to,
            system_from=self.system_from,
            system_to=now,
            payload=self.payload,
            provenance=self.provenance,
        )
        replacement = BiTemporalRecord(
            record_id=new_record_id,
            entity_key=self.entity_key,
            valid_from=new_valid_from if new_valid_from is not None else self.valid_from,
            valid_to=new_valid_to if new_valid_to is not None else self.valid_to,
            system_from=now,
            system_to=None,
            payload=new_payload,
            provenance=provenance,
        )
        return closed, replacement
