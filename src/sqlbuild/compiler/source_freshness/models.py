"""Standard source freshness state models."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from sqlbuild.adapter.contract.types import FrameworkType
from sqlbuild.compiler.source_freshness.types import SourceFreshnessAgeStatus
from sqlbuild.spec.contracts.types import SourceFreshnessStrategy, SourceFreshnessValueKind


@dataclass(frozen=True)
class SourceFreshnessRenderers:
    """Adapter SQL renderers used when writing source freshness rows."""

    render_qualified_name: Callable[..., str | None]
    render_framework_type: Callable[[FrameworkType], str]
    render_insert_records_sql: Callable[..., str]
    render_create_table_sql: Callable[..., str] | None = None
    render_create_index_sqls: Callable[..., tuple[str, ...]] | None = None


@dataclass(frozen=True)
class SourceFreshnessObservation:
    """One comparable source data-version observation."""

    source_name: str
    strategy: SourceFreshnessStrategy
    data_version: object
    value_kind: SourceFreshnessValueKind
    observed_at: datetime


@dataclass(frozen=True)
class SourceFreshnessIdentity:
    """Stable identity for one source freshness stream in standard state."""

    source_name: str
    target_database: str | None
    target_schema: str | None
    target_name: str | None


@dataclass(frozen=True)
class SourceFreshnessRecord:
    """One append-only standard source freshness observation."""

    source_name: str
    target_database: str | None
    target_schema: str | None
    target_name: str | None
    run_id: str
    strategy: str
    value_kind: str
    data_version: str | None
    data_version_hash: str
    observed_at: datetime

    @property
    def identity(self) -> SourceFreshnessIdentity:
        return SourceFreshnessIdentity(
            source_name=self.source_name,
            target_database=self.target_database,
            target_schema=self.target_schema,
            target_name=self.target_name,
        )


@dataclass(frozen=True)
class SourceFreshnessSet:
    """Latest standard source freshness records for one target schema."""

    schema: str
    records: dict[SourceFreshnessIdentity, SourceFreshnessRecord]


@dataclass(frozen=True)
class StandardSourceFreshnessPropagationResult:
    """Downstream model impact derived from standard source freshness roots."""

    changed_source_model_names: dict[SourceFreshnessIdentity, frozenset[str]] = field(
        default_factory=dict
    )
    unknown_source_model_names: dict[str, frozenset[str]] = field(default_factory=dict)
    error_source_model_names: dict[SourceFreshnessIdentity, frozenset[str]] = field(
        default_factory=dict
    )
    stale_model_names: frozenset[str] = frozenset()
    blocked_model_names: frozenset[str] = frozenset()


@dataclass(frozen=True)
class StandardSourceFreshnessPlanningResult:
    """Direct planning-time source freshness observations and comparisons."""

    observed_records: tuple[SourceFreshnessRecord, ...] = ()
    previous_records: tuple[SourceFreshnessRecord, ...] = ()
    changed_identities: frozenset[SourceFreshnessIdentity] = frozenset()
    unchanged_identities: frozenset[SourceFreshnessIdentity] = frozenset()
    unknown_source_names: tuple[str, ...] = ()
    age_statuses: dict[SourceFreshnessIdentity, SourceFreshnessAgeStatus] = field(
        default_factory=dict
    )
    propagation: StandardSourceFreshnessPropagationResult | None = None
