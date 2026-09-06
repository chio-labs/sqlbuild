"""Public authoring API for generated SQL audit attachments."""

from __future__ import annotations

from collections.abc import Callable
from typing import overload

from sqlbuild.compiler.auditing.models import (
    MeasurementThresholdBound,
    MeasurementThresholds,
)
from sqlbuild.compiler.auditing.types import AuditSeverity, ThresholdOperator
from sqlbuild.python_nodes.main.apply_audit_factory import apply_audit_factory
from sqlbuild.python_nodes.main.read_audit_factory_definition import (
    read_audit_factory_definition,
)
from sqlbuild.python_nodes.models import AuditCase, AuditFactoryDefinition

__all__ = (
    "AuditCase",
    "AuditSeverity",
    "MeasurementThresholdBound",
    "MeasurementThresholds",
    "ThresholdOperator",
    "above",
    "audit_factory",
    "below",
    "get_audit_factory_definition",
    "outside",
)


def below(limit: float) -> MeasurementThresholdBound:
    """Return a threshold that matches values below ``limit``."""

    return MeasurementThresholdBound(operator=ThresholdOperator.BELOW, limit=limit)


def above(limit: float) -> MeasurementThresholdBound:
    """Return a threshold that matches values above ``limit``."""

    return MeasurementThresholdBound(operator=ThresholdOperator.ABOVE, limit=limit)


def outside(*, lower: float, upper: float) -> MeasurementThresholdBound:
    """Return a threshold that matches values outside the inclusive range."""

    return MeasurementThresholdBound(
        operator=ThresholdOperator.OUTSIDE,
        lower=lower,
        upper=upper,
    )


@overload
def audit_factory(function: Callable[..., object]) -> Callable[..., object]: ...


@overload
def audit_factory(
    function: None = None,
) -> Callable[[Callable[..., object]], Callable[..., object]]: ...


def audit_factory(
    function: Callable[..., object] | None = None,
) -> Callable[..., object] | Callable[[Callable[..., object]], Callable[..., object]]:
    """Mark a deterministic, side-effect-free function as an audit-case factory."""

    if function is None:
        return apply_audit_factory
    return apply_audit_factory(function)


def get_audit_factory_definition(
    function: Callable[..., object],
) -> AuditFactoryDefinition | None:
    """Return audit-factory metadata from a decorated function, if present."""

    return read_audit_factory_definition(function)
