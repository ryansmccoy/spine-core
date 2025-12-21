"""Tests for spine.domain.finance.observations — financial dataclass models.

Covers MetricSpec, FiscalPeriod, ProvenanceRef, SourceKey, ValueWithUnits,
Observation, and ObservationSet.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

from spine.core.enums import ProvenanceKind, VendorNamespace
from spine.domain.finance.enums import (
    AccountingBasis,
    MetricCategory,
    MetricCode,
    ObservationType,
    PeriodType,
    PerShareType,
    Presentation,
    ScopeType,
)
from spine.domain.finance.observations import (
    FiscalPeriod,
    MetricSpec,
    Observation,
    ObservationSet,
    ProvenanceRef,
    SourceKey,
    ValueWithUnits,
)


# =============================================================================
# MetricSpec
# =============================================================================


class TestMetricSpec:
    """MetricSpec dataclass tests."""

    def test_basic_creation(self):
        spec = MetricSpec(code=MetricCode.REVENUE)
        assert spec.code == MetricCode.REVENUE
        assert spec.basis == AccountingBasis.GAAP
        assert spec.presentation == Presentation.REPORTED
        assert spec.category == MetricCategory.OTHER
        assert spec.per_share is None

    def test_eps_auto_sets_diluted(self):
        """EPS-like metrics auto-default to diluted per_share."""
        for code in (MetricCode.EPS, MetricCode.DPS, MetricCode.BPS, MetricCode.CFPS):
            spec = MetricSpec(code=code)
            assert spec.per_share == PerShareType.DILUTED, f"{code} should auto-set diluted"

    def test_eps_basic_override(self):
        spec = MetricSpec(code=MetricCode.EPS, per_share=PerShareType.BASIC)
        assert spec.per_share == PerShareType.BASIC

    def test_str_representation(self):
        spec = MetricSpec(code=MetricCode.REVENUE)
        assert "REVENUE" in str(spec)

    def test_str_with_qualifiers(self):
        spec = MetricSpec(
            code=MetricCode.EPS,
            basis=AccountingBasis.IFRS,
            presentation=Presentation.COMPANY_ADJUSTED,
            per_share=PerShareType.DILUTED,
            scope=ScopeType.CONTINUING,
        )
        s = str(spec)
        assert "EPS" in s
        assert "diluted" in s.lower() or "(diluted)" in s

    def test_canonical_key(self):
        spec = MetricSpec(code=MetricCode.REVENUE)
        key = spec.canonical_key
        assert "revenue" in key
        assert "gaap" in key
        assert "reported" in key

    def test_canonical_key_uniqueness(self):
        s1 = MetricSpec(code=MetricCode.EPS, per_share=PerShareType.BASIC)
        s2 = MetricSpec(code=MetricCode.EPS, per_share=PerShareType.DILUTED)
        assert s1.canonical_key != s2.canonical_key

    def test_factory_revenue(self):
        spec = MetricSpec.revenue()
        assert spec.code == MetricCode.REVENUE
        assert spec.category == MetricCategory.INCOME_STATEMENT

    def test_factory_eps_gaap_diluted(self):
        spec = MetricSpec.eps_gaap_diluted()
        assert spec.code == MetricCode.EPS
        assert spec.per_share == PerShareType.DILUTED
        assert spec.basis == AccountingBasis.GAAP

    def test_factory_eps_gaap_basic(self):
        spec = MetricSpec.eps_gaap_basic()
        assert spec.per_share == PerShareType.BASIC

    def test_factory_net_income(self):
        spec = MetricSpec.net_income()
        assert spec.code == MetricCode.NET_INCOME

    def test_factory_ebitda(self):
        spec = MetricSpec.ebitda()
        assert spec.code == MetricCode.EBITDA

    def test_factory_fcf(self):
        spec = MetricSpec.fcf()
        assert spec.code == MetricCode.FCF
        assert spec.category == MetricCategory.CASH_FLOW

    def test_frozen(self):
        spec = MetricSpec(code=MetricCode.REVENUE)
        with pytest.raises(AttributeError):
            spec.code = MetricCode.EPS  # type: ignore[misc]


# =============================================================================
# FiscalPeriod
# =============================================================================


class TestFiscalPeriod:
    """FiscalPeriod dataclass tests."""

    def test_annual(self):
        fp = FiscalPeriod.annual(2025)
        assert fp.fiscal_year == 2025
        assert fp.period_type == PeriodType.ANNUAL
        assert str(fp) == "FY2025"

    def test_quarterly(self):
        fp = FiscalPeriod.quarterly(2025, 4)
        assert fp.quarter == 4
        assert "Q4" in str(fp)

    def test_quarterly_validation(self):
        with pytest.raises(ValueError, match="quarter 1-4"):
            FiscalPeriod(fiscal_year=2025, period_type=PeriodType.QUARTERLY, quarter=5)

    def test_quarterly_none_quarter(self):
        with pytest.raises(ValueError, match="quarter 1-4"):
            FiscalPeriod(fiscal_year=2025, period_type=PeriodType.QUARTERLY)

    def test_semi_annual(self):
        fp = FiscalPeriod.semi_annual(2025, 1)
        assert fp.half == 1
        assert "H1" in str(fp)

    def test_semi_annual_validation(self):
        with pytest.raises(ValueError, match="half 1-2"):
            FiscalPeriod(fiscal_year=2025, period_type=PeriodType.SEMI_ANNUAL, half=3)

    def test_ttm(self):
        fp = FiscalPeriod.ttm(2025, ending_quarter=3)
        assert fp.period_type == PeriodType.TTM
        assert "TTM" in str(fp)
        assert "Q3" in str(fp)

    def test_ttm_no_quarter(self):
        fp = FiscalPeriod.ttm(2025)
        assert "TTM" in str(fp)

    def test_other_period_type_str(self):
        fp = FiscalPeriod(fiscal_year=2025, period_type=PeriodType.YTD)
        assert "ytd" in str(fp).lower()

    def test_canonical_key(self):
        fp = FiscalPeriod.annual(2025)
        key = fp.canonical_key
        assert "2025" in key
        assert "annual" in key

    def test_canonical_key_uniqueness(self):
        q1 = FiscalPeriod.quarterly(2025, 1)
        q2 = FiscalPeriod.quarterly(2025, 2)
        assert q1.canonical_key != q2.canonical_key

    def test_frozen(self):
        fp = FiscalPeriod.annual(2025)
        with pytest.raises(AttributeError):
            fp.fiscal_year = 2024  # type: ignore[misc]


# =============================================================================
# ProvenanceRef
# =============================================================================


class TestProvenanceRef:
    """ProvenanceRef dataclass tests."""

    def test_sec_filing_factory(self):
        prov = ProvenanceRef.sec_filing(
            accession_number="0001234-25-000001",
            form_type="10-K",
            filing_date=date(2025, 2, 15),
        )
        assert prov.kind == ProvenanceKind.SEC_FILING
        assert prov.accession_number == "0001234-25-000001"
        assert prov.form_type == "10-K"
        assert prov.filing_date == date(2025, 2, 15)

    def test_vendor_snapshot_factory(self):
        prov = ProvenanceRef.vendor_snapshot(
            vendor=VendorNamespace.SEC,
            snapshot_date=date(2025, 1, 15),
        )
        assert prov.kind == ProvenanceKind.VENDOR_SNAPSHOT

    def test_press_release_factory(self):
        prov = ProvenanceRef.press_release(
            release_date=date(2025, 1, 20),
            url="https://example.com/pr",
        )
        assert prov.kind == ProvenanceKind.PRESS_RELEASE
        assert prov.document_url == "https://example.com/pr"

    def test_str(self):
        prov = ProvenanceRef.sec_filing(
            accession_number="0001234-25-000001",
            form_type="10-K",
            filing_date=date(2025, 2, 15),
        )
        assert "sec_filing" in str(prov)

    def test_empty_external_id_raises(self):
        with pytest.raises(ValueError, match="external_id"):
            ProvenanceRef(kind=ProvenanceKind.SEC_FILING, external_id="   ")

    def test_provenance_id_generated(self):
        prov = ProvenanceRef(kind=ProvenanceKind.SEC_FILING, external_id="test-123")
        assert prov.provenance_id  # not empty


# =============================================================================
# SourceKey
# =============================================================================


class TestSourceKey:
    """SourceKey dataclass tests."""

    def test_sec_xbrl(self):
        sk = SourceKey.sec_xbrl("Revenues", namespace="us-gaap")
        assert sk.xbrl_tag == "Revenues"
        assert sk.vendor == VendorNamespace.SEC
        assert "us-gaap" in str(sk)

    def test_from_vendor(self):
        sk = SourceKey.from_vendor(VendorNamespace.SEC, "FF_SALES", dataset="fundamentals")
        assert sk.field_name == "FF_SALES"

    def test_str_xbrl(self):
        sk = SourceKey.sec_xbrl("NetIncomeLoss")
        assert "NetIncomeLoss" in str(sk)

    def test_str_vendor(self):
        sk = SourceKey.from_vendor(VendorNamespace.SEC, "FF_SALES")
        assert "FF_SALES" in str(sk)

    def test_str_unknown(self):
        sk = SourceKey()
        assert str(sk) == "unknown"


# =============================================================================
# ValueWithUnits
# =============================================================================


class TestValueWithUnits:
    """ValueWithUnits dataclass tests."""

    def test_from_raw(self):
        v = ValueWithUnits.from_raw(Decimal("119.2"), "USD", scale=1_000_000)
        assert v.value_raw == Decimal("119.2")
        assert v.value_normalized == Decimal("119200000.0")

    def test_from_normalized(self):
        v = ValueWithUnits.from_normalized(Decimal("119200000"), "USD", scale=1_000_000)
        assert v.value_normalized == Decimal("119200000")
        assert v.value_raw == Decimal("119.2")

    def test_in_millions(self):
        v = ValueWithUnits.from_raw(Decimal("119200000"), "USD")
        assert v.in_millions() == Decimal("119.2")

    def test_in_billions(self):
        v = ValueWithUnits.from_raw(Decimal("119200000000"), "USD")
        assert v.in_billions() == Decimal("119.2")

    def test_negative_scale_raises(self):
        with pytest.raises(ValueError, match="scale must be positive"):
            ValueWithUnits(
                value_normalized=Decimal("100"),
                value_raw=Decimal("100"),
                unit="USD",
                scale=-1,
            )

    def test_zero_scale_raises(self):
        with pytest.raises(ValueError, match="scale must be positive"):
            ValueWithUnits(
                value_normalized=Decimal("100"),
                value_raw=Decimal("100"),
                unit="USD",
                scale=0,
            )

    def test_str_with_currency(self):
        v = ValueWithUnits.from_raw(Decimal("100"), "USD", currency="USD")
        assert "USD" in str(v)

    def test_str_without_currency(self):
        v = ValueWithUnits.from_raw(Decimal("42.5"), "%")
        assert "%" in str(v)


# =============================================================================
# Observation
# =============================================================================


class TestObservation:
    """Observation dataclass tests."""

    def _make_observation(self, **kwargs) -> Observation:
        """Helper to create an observation with defaults."""
        defaults = dict(
            entity_id="AAPL",
            metric=MetricSpec.revenue(),
            period=FiscalPeriod.annual(2025),
            value=ValueWithUnits.from_raw(Decimal("394328"), "USD", scale=1_000_000),
        )
        defaults.update(kwargs)
        return Observation(**defaults)

    def test_basic_creation(self):
        obs = self._make_observation()
        assert obs.entity_id == "AAPL"
        assert obs.metric.code == MetricCode.REVENUE
        assert obs.observation_type == ObservationType.ACTUAL
        assert obs.confidence == 1.0
        assert obs.observation_id  # auto-generated

    def test_empty_entity_raises(self):
        with pytest.raises(ValueError, match="entity_id"):
            self._make_observation(entity_id="   ")

    def test_invalid_confidence_raises(self):
        with pytest.raises(ValueError, match="confidence"):
            self._make_observation(confidence=1.5)

    def test_negative_confidence_raises(self):
        with pytest.raises(ValueError, match="confidence"):
            self._make_observation(confidence=-0.1)

    def test_observation_key_deterministic(self):
        """Same inputs should produce same key."""
        obs1 = self._make_observation(observation_id="a")
        obs2 = self._make_observation(observation_id="b")
        # observation_id differs but observation_key should be same (based on entity/metric/period)
        assert obs1.observation_key == obs2.observation_key

    def test_observation_key_differs_by_entity(self):
        obs1 = self._make_observation(entity_id="AAPL")
        obs2 = self._make_observation(entity_id="MSFT")
        assert obs1.observation_key != obs2.observation_key

    def test_repr(self):
        obs = self._make_observation()
        r = repr(obs)
        assert "AAPL" in r
        assert "REVENUE" in r or "Observation" in r

    def test_with_provenance(self):
        prov = ProvenanceRef.sec_filing(
            accession_number="0001234-25-000001",
            form_type="10-K",
            filing_date=date(2025, 2, 15),
        )
        obs = self._make_observation(provenance_ref=prov)
        assert obs.provenance_ref is not None
        assert obs.provenance_ref.form_type == "10-K"

    def test_with_source_key(self):
        sk = SourceKey.sec_xbrl("Revenues")
        obs = self._make_observation(source_key=sk)
        assert obs.source_key.xbrl_tag == "Revenues"


# =============================================================================
# ObservationSet
# =============================================================================


class TestObservationSet:
    """ObservationSet collection tests."""

    def _make_obs(self, obs_type: ObservationType = ObservationType.ACTUAL, **kwargs) -> Observation:
        defaults = dict(
            entity_id="AAPL",
            metric=MetricSpec.revenue(),
            period=FiscalPeriod.annual(2025),
            value=ValueWithUnits.from_raw(Decimal("394328"), "USD", scale=1_000_000),
            observation_type=obs_type,
        )
        defaults.update(kwargs)
        return Observation(**defaults)

    def test_empty_set(self):
        obs_set = ObservationSet(
            entity_id="AAPL",
            metric=MetricSpec.revenue(),
            period=FiscalPeriod.annual(2025),
        )
        assert len(obs_set.observations) == 0
        assert obs_set.get_actuals() == []
        assert obs_set.get_estimates() == []
        assert obs_set.get_consensus() is None

    def test_get_by_type(self):
        actual = self._make_obs(ObservationType.ACTUAL)
        estimate = self._make_obs(ObservationType.ESTIMATE)
        obs_set = ObservationSet(
            entity_id="AAPL",
            metric=MetricSpec.revenue(),
            period=FiscalPeriod.annual(2025),
            observations=[actual, estimate],
        )
        assert len(obs_set.get_actuals()) == 1
        assert len(obs_set.get_estimates()) == 1

    def test_get_consensus(self):
        consensus = self._make_obs(ObservationType.CONSENSUS)
        obs_set = ObservationSet(
            entity_id="AAPL",
            metric=MetricSpec.revenue(),
            period=FiscalPeriod.annual(2025),
            observations=[consensus],
        )
        assert obs_set.get_consensus() is consensus

    def test_get_latest_actual(self):
        old = self._make_obs(as_of=datetime(2025, 1, 1))
        new = self._make_obs(as_of=datetime(2025, 6, 1))
        obs_set = ObservationSet(
            entity_id="AAPL",
            metric=MetricSpec.revenue(),
            period=FiscalPeriod.annual(2025),
            observations=[old, new],
        )
        latest = obs_set.get_latest_actual()
        assert latest is not None
        assert latest.as_of == datetime(2025, 6, 1)

    def test_get_latest_actual_empty(self):
        obs_set = ObservationSet(
            entity_id="AAPL",
            metric=MetricSpec.revenue(),
            period=FiscalPeriod.annual(2025),
        )
        assert obs_set.get_latest_actual() is None

    def test_get_authoritative_actual_prefers_sec(self):
        prov = ProvenanceRef.sec_filing(
            accession_number="0001234-25-000001",
            form_type="10-K",
            filing_date=date(2025, 2, 15),
        )
        sec_actual = self._make_obs(
            provenance_ref=prov,
            as_of=datetime(2025, 2, 15),
        )
        vendor_actual = self._make_obs(
            as_of=datetime(2025, 3, 1),  # newer but not SEC
        )
        obs_set = ObservationSet(
            entity_id="AAPL",
            metric=MetricSpec.revenue(),
            period=FiscalPeriod.annual(2025),
            observations=[sec_actual, vendor_actual],
        )
        auth = obs_set.get_authoritative_actual()
        assert auth is sec_actual

    def test_get_authoritative_actual_no_observations(self):
        obs_set = ObservationSet(
            entity_id="AAPL",
            metric=MetricSpec.revenue(),
            period=FiscalPeriod.annual(2025),
        )
        assert obs_set.get_authoritative_actual() is None

    def test_get_authoritative_actual_superseded_excluded(self):
        """Superseded observations should be excluded from authoritative."""
        superseded = self._make_obs(
            as_of=datetime(2025, 2, 15),
            superseded_by_id="newer-obs-id",
        )
        obs_set = ObservationSet(
            entity_id="AAPL",
            metric=MetricSpec.revenue(),
            period=FiscalPeriod.annual(2025),
            observations=[superseded],
        )
        assert obs_set.get_authoritative_actual() is None
