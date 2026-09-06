"""Auditing identity models."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import cast

from sqlbuild.compiler.auditing.exceptions import MeasurementAuditError
from sqlbuild.compiler.auditing.types import AuditSeverity, ThresholdOperator


@dataclass(frozen=True, kw_only=True)
class MeasurementThresholdBound:
    """One directional threshold bound for a measurement audit."""

    operator: ThresholdOperator
    limit: float | None = None
    lower: float | None = None
    upper: float | None = None

    def __post_init__(self) -> None:
        if self.operator in {ThresholdOperator.BELOW, ThresholdOperator.ABOVE}:
            if self.limit is None or self.lower is not None or self.upper is not None:
                raise MeasurementAuditError(f"{self.operator.value} threshold requires limit only")
            if isinstance(self.limit, bool):
                raise MeasurementAuditError("measurement threshold limit must not be boolean")
            object.__setattr__(self, "limit", float(self.limit))
            if not isfinite(self.limit):
                raise MeasurementAuditError("measurement threshold limit must be finite")
            return

        if self.limit is not None or self.lower is None or self.upper is None:
            raise MeasurementAuditError("outside threshold requires lower and upper only")
        if isinstance(self.lower, bool):
            raise MeasurementAuditError("measurement threshold lower must not be boolean")
        if isinstance(self.upper, bool):
            raise MeasurementAuditError("measurement threshold upper must not be boolean")
        object.__setattr__(self, "lower", float(self.lower))
        object.__setattr__(self, "upper", float(self.upper))
        if not isfinite(self.lower):
            raise MeasurementAuditError("measurement threshold lower must be finite")
        if not isfinite(self.upper):
            raise MeasurementAuditError("measurement threshold upper must be finite")
        if self.lower > self.upper:
            raise MeasurementAuditError(
                "outside threshold lower must be less than or equal to upper"
            )


@dataclass(frozen=True, kw_only=True)
class MeasurementThresholds:
    """Warning and error policy for a measurement audit."""

    warn: MeasurementThresholdBound | None = None
    error: MeasurementThresholdBound | None = None

    def __post_init__(self) -> None:
        if self.warn is None and self.error is None:
            raise MeasurementAuditError("at least one measurement threshold is required")
        if self.warn is None or self.error is None:
            return
        if self.warn.operator != self.error.operator:
            raise MeasurementAuditError(
                "mixed measurement threshold operators are unsupported in v1"
            )
        if self.warn.operator == ThresholdOperator.BELOW:
            if cast(float, self.error.limit) >= cast(float, self.warn.limit):
                raise MeasurementAuditError("below error limit must be less than warn limit")
            return
        if self.warn.operator == ThresholdOperator.ABOVE:
            if cast(float, self.error.limit) <= cast(float, self.warn.limit):
                raise MeasurementAuditError("above error limit must be greater than warn limit")
            return
        if cast(float, self.error.lower) >= cast(float, self.warn.lower) or cast(
            float, self.error.upper
        ) <= cast(float, self.warn.upper):
            raise MeasurementAuditError("outside error range must strictly contain warn range")


@dataclass(frozen=True, kw_only=True)
class MeasurementContract:
    """Columns and sample unit returned by a measurement query."""

    value_column: str
    sample_count_column: str | None = None
    sample_unit: str | None = None

    def __post_init__(self) -> None:
        if not self.value_column.strip():
            raise MeasurementAuditError("measurement contract value_column must be non-empty")
        if self.sample_count_column is not None and not self.sample_count_column.strip():
            raise MeasurementAuditError(
                "measurement contract sample_count_column must be non-empty"
            )
        if self.sample_unit is not None and not self.sample_unit.strip():
            raise MeasurementAuditError("measurement contract sample_unit must be non-empty")


@dataclass(frozen=True)
class AuditIdentity:
    """Stable identity values for one planned audit binding."""

    binding_key: str
    audit_name: str
    definition_fingerprint: str
    execution_fingerprint: str
    severity: AuditSeverity
    run_scope_phase: str
    attachment_kind: str
    attached_target_name: str | None = None
    attached_column_name: str | None = None
    always_run: bool = False


@dataclass(frozen=True)
class AuditGateIdentity:
    """Aggregate identity for a model's runtime audit gate."""

    binding_set_hash: str
    blocking_set_hash: str
    audits: tuple[AuditIdentity, ...]
