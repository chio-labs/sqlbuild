"""Schema-attached audit parsing implementation."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from sqlbuild.compiler.auditing.constants import (
    MEASUREMENT_OUTSIDE_BOUND_VALUE_COUNT,
    MEASUREMENT_THRESHOLD_ERROR_KEY,
    MEASUREMENT_THRESHOLD_WARN_KEY,
    SCHEMA_AUDIT_OPTION_KEYS,
)
from sqlbuild.compiler.auditing.exceptions import MeasurementAuditError
from sqlbuild.compiler.auditing.models import MeasurementThresholdBound, MeasurementThresholds
from sqlbuild.compiler.auditing.types import AuditSeverity, ThresholdOperator
from sqlbuild.compiler.resource_names.main._validate_resource_identity import (
    validate_resource_identity,
)
from sqlbuild.spec.contracts.models import SchemaAuditInstance


def parse_audit_instance_impl(
    *,
    raw_audit: object,
    file_path: Path,
    label: str,
    error_class: type[Exception],
) -> SchemaAuditInstance:
    """Parse one audit instance from a raw mapping or string value."""

    if isinstance(raw_audit, str):
        if not raw_audit.strip():
            raise error_class(f"{file_path} {label} audits must not contain empty names")
        validate_resource_identity(
            name=raw_audit,
            kind=f"{label} audit definition",
            path=file_path,
        )
        return SchemaAuditInstance(definition_name=raw_audit)

    if not isinstance(raw_audit, dict) or len(raw_audit) != 1:
        raise error_class(f"{file_path} {label} audits must be strings or single-key mappings")

    typed_audit_mapping: dict[str, object] = cast(dict[str, object], raw_audit)
    definition_name: str = next(iter(typed_audit_mapping))
    if not isinstance(definition_name, str) or not definition_name.strip():
        raise error_class(f"{file_path} {label} audit names must be non-empty strings")
    validate_resource_identity(
        name=definition_name,
        kind=f"{label} audit definition",
        path=file_path,
    )

    raw_arguments: object = typed_audit_mapping[definition_name]
    if raw_arguments is None:
        return SchemaAuditInstance(definition_name=definition_name)
    if not isinstance(raw_arguments, dict):
        raise error_class(
            f"{file_path} {label} audit '{definition_name}' arguments must be a mapping"
        )

    argument_mapping: dict[str, object] = cast(dict[str, object], raw_arguments)
    option_label: str = f"{label} audit '{definition_name}'"
    name: str | None = _optional_named_string(
        raw_value=argument_mapping.get("name"),
        file_path=file_path,
        label=option_label,
        key="name",
        error_class=error_class,
    )
    if name is not None:
        validate_resource_identity(
            name=name,
            kind=f"{label} audit instance",
            path=file_path,
        )
    description: str | None = _optional_named_string(
        raw_value=argument_mapping.get("description"),
        file_path=file_path,
        label=option_label,
        key="description",
        error_class=error_class,
    )
    raw_severity: str | None = _optional_named_string(
        raw_value=argument_mapping.get("severity"),
        file_path=file_path,
        label=option_label,
        key="severity",
        error_class=error_class,
    )
    severity: AuditSeverity | None = None
    if raw_severity is not None:
        try:
            severity = AuditSeverity(raw_severity)
        except ValueError as error:
            allowed: str = ", ".join(item.value for item in AuditSeverity)
            raise error_class(
                f"{file_path} {option_label} 'severity' must be one of: {allowed}"
            ) from error
    run_scope: str | None = _optional_named_string(
        raw_value=argument_mapping.get("run_scope"),
        file_path=file_path,
        label=option_label,
        key="run_scope",
        error_class=error_class,
    )
    always_run: bool = _optional_named_bool(
        raw_value=argument_mapping.get("always_run"),
        file_path=file_path,
        label=option_label,
        key="always_run",
        error_class=error_class,
    )
    thresholds: MeasurementThresholds | None = parse_measurement_thresholds(
        raw_value=argument_mapping.get("thresholds"),
        file_path=file_path,
        label=option_label,
        error_class=error_class,
    )
    minimum_samples: int | None = parse_minimum_samples(
        raw_value=argument_mapping.get("minimum_samples"),
        file_path=file_path,
        label=option_label,
        error_class=error_class,
    )
    evidence_limit: int | None = parse_evidence_limit(
        raw_value=argument_mapping.get("evidence_limit"),
        file_path=file_path,
        label=option_label,
        error_class=error_class,
    )
    arguments: dict[str, object] = {
        key: value for key, value in argument_mapping.items() if key not in SCHEMA_AUDIT_OPTION_KEYS
    }
    return SchemaAuditInstance(
        definition_name=definition_name,
        arguments=arguments,
        name=name,
        description=description,
        severity=severity,
        run_scope=run_scope,
        always_run=always_run,
        thresholds=thresholds,
        minimum_samples=minimum_samples,
        evidence_limit=evidence_limit,
    )


def parse_measurement_thresholds(
    *,
    raw_value: object | None,
    file_path: Path,
    label: str,
    error_class: type[Exception],
) -> MeasurementThresholds | None:
    """Parse authored warn/error directional measurement thresholds."""

    if raw_value is None:
        return None
    if not isinstance(raw_value, dict):
        raise error_class(f"{file_path} {label} 'thresholds' must be a mapping")
    threshold_mapping: dict[str, object] = cast(dict[str, object], raw_value)
    unknown: tuple[str, ...] = tuple(
        key
        for key in threshold_mapping
        if key not in {MEASUREMENT_THRESHOLD_WARN_KEY, MEASUREMENT_THRESHOLD_ERROR_KEY}
    )
    if unknown:
        raise error_class(
            f"{file_path} {label} 'thresholds' has unsupported keys: {', '.join(unknown)}"
        )
    try:
        return MeasurementThresholds(
            warn=_parse_threshold_bound(threshold_mapping.get(MEASUREMENT_THRESHOLD_WARN_KEY)),
            error=_parse_threshold_bound(threshold_mapping.get(MEASUREMENT_THRESHOLD_ERROR_KEY)),
        )
    except MeasurementAuditError as error:
        raise error_class(f"{file_path} {label} invalid thresholds: {error}") from error


def parse_minimum_samples(
    *,
    raw_value: object | None,
    file_path: Path,
    label: str,
    error_class: type[Exception],
) -> int | None:
    """Parse an optional non-negative minimum sample requirement."""

    if raw_value is None:
        return None
    if isinstance(raw_value, bool) or not isinstance(raw_value, int) or raw_value < 0:
        raise error_class(f"{file_path} {label} 'minimum_samples' must be a non-negative integer")
    return raw_value


def parse_evidence_limit(
    *,
    raw_value: object | None,
    file_path: Path,
    label: str,
    error_class: type[Exception],
) -> int | None:
    """Parse an optional non-negative retained evidence row limit."""

    if raw_value is None:
        return None
    if isinstance(raw_value, bool) or not isinstance(raw_value, int) or raw_value < 0:
        raise error_class(f"{file_path} {label} 'evidence_limit' must be a non-negative integer")
    return raw_value


def _parse_threshold_bound(raw_value: object | None) -> MeasurementThresholdBound | None:
    if raw_value is None:
        return None
    if not isinstance(raw_value, dict) or len(raw_value) != 1:
        raise MeasurementAuditError(
            "each threshold must be exactly one of below, above, or outside"
        )
    bound_mapping: dict[str, object] = cast(dict[str, object], raw_value)
    raw_operator, raw_limit = next(iter(bound_mapping.items()))
    try:
        operator: ThresholdOperator = ThresholdOperator(raw_operator)
    except ValueError as error:
        raise MeasurementAuditError(
            "threshold operator must be one of below, above, or outside"
        ) from error
    if operator == ThresholdOperator.OUTSIDE:
        if (
            not isinstance(raw_limit, tuple)
            or len(raw_limit) != MEASUREMENT_OUTSIDE_BOUND_VALUE_COUNT
            or any(
                isinstance(item, bool) or not isinstance(item, (int, float)) for item in raw_limit
            )
        ):
            raise MeasurementAuditError("outside threshold requires two numeric values")
        lower, upper = cast(tuple[int | float, int | float], raw_limit)
        return MeasurementThresholdBound(
            operator=operator,
            lower=float(lower),
            upper=float(upper),
        )
    if isinstance(raw_limit, bool) or not isinstance(raw_limit, (int, float)):
        raise MeasurementAuditError(f"{operator.value} threshold requires one numeric value")
    return MeasurementThresholdBound(operator=operator, limit=float(raw_limit))


def _optional_named_string(
    *,
    raw_value: object | None,
    file_path: Path,
    label: str,
    key: str,
    error_class: type[Exception],
) -> str | None:
    if raw_value is None:
        return None
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise error_class(f"{file_path} {label} '{key}' must be a non-empty string")
    return raw_value


def _optional_named_bool(
    *,
    raw_value: object | None,
    file_path: Path,
    label: str,
    key: str,
    error_class: type[Exception],
) -> bool:
    if raw_value is None:
        return False
    if not isinstance(raw_value, bool):
        raise error_class(f"{file_path} {label} '{key}' must be a boolean")
    return raw_value
