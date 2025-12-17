"""
Financial domain primitives for the spine ecosystem.

STDLIB ONLY - NO PYDANTIC.

This package provides the core observation and metric models that are
reusable across any spine project dealing with financial data. These
are the universal primitives; market-spine extends them with vendor-
specific factory methods and estimate/earnings models.

Models:
    Observation: A single data point with 3D time semantics
    ObservationSet: Collection for comparison/analysis
    MetricSpec: Structured metric specification with orthogonal axes
    FiscalPeriod: Fiscal period representation
    ValueWithUnits: Numeric value with explicit units and scale
    ProvenanceRef: Document-level data lineage
    SourceKey: Field-level data provenance

Enums (in .enums):
    MetricCode, MetricCategory, AccountingBasis, Presentation,
    PerShareType, ScopeType, PeriodType, ObservationType
"""

from spine.domain.finance.observations import (
    FiscalPeriod,
    MetricSpec,
    Observation,
    ObservationSet,
    ProvenanceRef,
    SourceKey,
    ValueWithUnits,
)

__all__ = [
    "FiscalPeriod",
    "MetricSpec",
    "Observation",
    "ObservationSet",
    "ProvenanceRef",
    "SourceKey",
    "ValueWithUnits",
]
