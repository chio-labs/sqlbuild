"""Source freshness command models."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from sqlbuild.cli.commands._helpers.freshness.types import FreshnessSourceStatus
from sqlbuild.compiler.source_freshness.types import SourceFreshnessAgeStatus


@dataclass(frozen=True)
class FreshnessCommandRequest:
    """CLI inputs for one `sqb freshness` invocation."""

    project_dir: Path | None = None
    no_sql_validation: bool = False
    no_color: bool = False
    selected_target: str | None = None
    select: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    cli_vars: dict[str, object] | None = None
    json_output: bool = False
    json_output_path: Path | None = None
    fail_on_error: bool = False
    compare_state: bool = False
    fail_on_stale: bool = False
    virtual_environment_name: str | None = None


@dataclass(frozen=True)
class FreshnessSourceResult:
    """Freshness observation result for one source."""

    name: str
    status: FreshnessSourceStatus
    strategy: str | None = None
    value_kind: str | None = None
    current_data_version: str | None = None
    previous_data_version: str | None = None
    lag_tolerance: str | None = None
    target_database: str | None = None
    target_schema: str | None = None
    target_name: str | None = None
    message: str | None = None
    age_status: SourceFreshnessAgeStatus | None = None


@dataclass(frozen=True)
class FreshnessCommandResult:
    """Source freshness command output payload."""

    sources: tuple[FreshnessSourceResult, ...] = field(default_factory=tuple)

    @property
    def observed_count(self) -> int:
        return sum(1 for source in self.sources if source.status == FreshnessSourceStatus.OBSERVED)

    @property
    def changed_count(self) -> int:
        return sum(1 for source in self.sources if source.status == FreshnessSourceStatus.CHANGED)

    @property
    def unchanged_count(self) -> int:
        return sum(1 for source in self.sources if source.status == FreshnessSourceStatus.UNCHANGED)

    @property
    def tolerated_count(self) -> int:
        return sum(1 for source in self.sources if source.status == FreshnessSourceStatus.TOLERATED)

    @property
    def unknown_count(self) -> int:
        return sum(1 for source in self.sources if source.status == FreshnessSourceStatus.UNKNOWN)

    @property
    def error_count(self) -> int:
        return sum(1 for source in self.sources if source.status == FreshnessSourceStatus.ERROR)

    @property
    def age_pass_count(self) -> int:
        return sum(
            1 for source in self.sources if source.age_status == SourceFreshnessAgeStatus.PASS
        )

    @property
    def age_warn_count(self) -> int:
        return sum(
            1 for source in self.sources if source.age_status == SourceFreshnessAgeStatus.WARN
        )

    @property
    def age_error_count(self) -> int:
        return sum(
            1 for source in self.sources if source.age_status == SourceFreshnessAgeStatus.ERROR
        )

    @property
    def age_unknown_count(self) -> int:
        return sum(
            1 for source in self.sources if source.age_status == SourceFreshnessAgeStatus.UNKNOWN
        )
