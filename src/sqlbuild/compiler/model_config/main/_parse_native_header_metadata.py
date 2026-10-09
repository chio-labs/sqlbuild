"""Parse a MODEL header's columns and audits natively."""

from __future__ import annotations

from pathlib import Path

import sqlbuild._native as _native
from sqlbuild.compiler.auditing.models import MeasurementThresholdBound, MeasurementThresholds
from sqlbuild.compiler.auditing.types import AuditSeverity, ThresholdOperator
from sqlbuild.compiler.model_config.models import NativeHeaderMetadata
from sqlbuild.compiler.model_config.types import NativeHeaderMetadataRow
from sqlbuild.spec.contracts.models import SchemaAuditInstance, SchemaColumn, SourceLocation

_CONTRACT_CLASSES: dict[str, object] = {
    "schema_column": SchemaColumn,
    "schema_audit_instance": SchemaAuditInstance,
    "measurement_thresholds": MeasurementThresholds,
    "measurement_threshold_bound": MeasurementThresholdBound,
    "severities": {severity.value: severity for severity in AuditSeverity},
    "threshold_operators": {operator.value: operator for operator in ThresholdOperator},
    "allocate": object.__new__,
}


def parse_native_header_metadata(
    *,
    raw_columns: object | None,
    raw_audits: object | None,
    column_locations: dict[str, SourceLocation],
    file_path: Path,
) -> NativeHeaderMetadata:
    """Return one model's header columns and audits, or the error each raises."""

    row: NativeHeaderMetadataRow = _native.parse_model_header_metadata(
        raw_columns, raw_audits, column_locations, str(file_path), _CONTRACT_CLASSES
    )
    columns, audits = row
    return NativeHeaderMetadata(
        columns=() if isinstance(columns, _native.NativeConfigError) else columns,
        audits=() if audits is None or isinstance(audits, _native.NativeConfigError) else audits,
        columns_error=columns if isinstance(columns, _native.NativeConfigError) else None,
        audits_error=audits if isinstance(audits, _native.NativeConfigError) else None,
    )
