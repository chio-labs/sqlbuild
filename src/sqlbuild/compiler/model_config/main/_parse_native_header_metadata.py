"""Parse MODEL header columns and audits natively for the preview compiler engine."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import fields
from pathlib import Path

import sqlbuild._native as _native
from sqlbuild.compiler.auditing.types import AuditSeverity
from sqlbuild.compiler.discovery.models import DiscoveredSqlModelFile
from sqlbuild.compiler.model_config.constants import (
    AUDITS_HEADER_KEY,
    COLUMNS_HEADER_KEY,
    INVALID_OUTCOME,
    SCHEMA_AUDIT_INSTANCE_FIELDS,
    SCHEMA_COLUMN_FIELDS,
    UNSUPPORTED_OUTCOME,
)
from sqlbuild.compiler.model_config.models import NativeHeaderMetadata
from sqlbuild.spec.contracts.models import SchemaAuditInstance, SchemaColumn


def parse_native_header_metadata(
    *, model_files: Sequence[DiscoveredSqlModelFile]
) -> dict[Path, NativeHeaderMetadata]:
    """Return native header metadata by model file; models Python must parse are absent."""

    if not model_files or not _contract_shapes_match():
        return {}
    try:
        parsed: list[tuple[tuple[SchemaColumn, ...], tuple[SchemaAuditInstance, ...]] | str] = (
            _native.parse_model_header_metadata(
                [
                    (
                        model_file.header_values.get(COLUMNS_HEADER_KEY),
                        model_file.header_values.get(AUDITS_HEADER_KEY),
                        model_file.header_column_locations,
                    )
                    for model_file in model_files
                ],
                {
                    "schema_column": SchemaColumn,
                    "schema_audit_instance": SchemaAuditInstance,
                    "severities": {severity.value: severity for severity in AuditSeverity},
                    "allocate": object.__new__,
                },
            )
        )
    except (TypeError, ValueError):
        return {}
    return {
        model_file.file_path: _native_metadata(model_file=model_file, metadata=metadata)
        for model_file, metadata in zip(model_files, parsed, strict=True)
        if metadata != UNSUPPORTED_OUTCOME
    }


def _native_metadata(
    *,
    model_file: DiscoveredSqlModelFile,
    metadata: tuple[tuple[SchemaColumn, ...], tuple[SchemaAuditInstance, ...]] | str,
) -> NativeHeaderMetadata:
    columns, audits = ((), ()) if isinstance(metadata, str) else metadata
    return NativeHeaderMetadata(
        raw_columns=model_file.header_values.get(COLUMNS_HEADER_KEY),
        raw_audits=model_file.header_values.get(AUDITS_HEADER_KEY),
        column_locations=model_file.header_column_locations,
        columns=columns,
        audits=audits,
        invalid=metadata == INVALID_OUTCOME,
    )


def _contract_shapes_match() -> bool:
    return (
        tuple(field.name for field in fields(SchemaColumn)) == SCHEMA_COLUMN_FIELDS
        and tuple(field.name for field in fields(SchemaAuditInstance))
        == SCHEMA_AUDIT_INSTANCE_FIELDS
        and not hasattr(SchemaColumn, "__post_init__")
        and not hasattr(SchemaAuditInstance, "__post_init__")
    )
