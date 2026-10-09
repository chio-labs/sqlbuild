"""Parse MODEL header columns and audits natively for the preview compiler engine."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import fields
from pathlib import Path

import sqlbuild._native as _native
from sqlbuild.compiler.auditing.types import AuditSeverity
from sqlbuild.compiler.discovery.models import DiscoveredSqlModelFile
from sqlbuild.compiler.frontier.main._report_native_fallback import report_native_fallback
from sqlbuild.compiler.frontier.types import NativeFallbackSite
from sqlbuild.compiler.model_config.constants import (
    AUDITS_HEADER_KEY,
    COLUMNS_HEADER_KEY,
    SCHEMA_AUDIT_INSTANCE_FIELDS,
    SCHEMA_COLUMN_FIELDS,
    UNSUPPORTED_OUTCOME,
)
from sqlbuild.compiler.model_config.models import NativeHeaderMetadata
from sqlbuild.compiler.model_config.types import NativeHeaderMetadataRow
from sqlbuild.spec.contracts.models import SchemaAuditInstance, SchemaColumn


def parse_native_header_metadata(
    *, model_files: Sequence[DiscoveredSqlModelFile]
) -> dict[Path, NativeHeaderMetadata]:
    """Return native header metadata by model file; models Python must parse are absent."""

    if not model_files or not _contract_shapes_match():
        return {}
    try:
        parsed: list[NativeHeaderMetadataRow | str] = _native.parse_model_header_metadata(
            [
                (
                    model_file.header_values.get(COLUMNS_HEADER_KEY),
                    model_file.header_values.get(AUDITS_HEADER_KEY),
                    model_file.header_column_locations,
                    str(model_file.relative_path),
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
    except (TypeError, ValueError):
        report_native_fallback(site=NativeFallbackSite.CONFIG_HEADER_METADATA, kind="batch")
        return {}
    for metadata in parsed:
        if metadata == UNSUPPORTED_OUTCOME:
            report_native_fallback(
                site=NativeFallbackSite.CONFIG_HEADER_METADATA, kind="unsupported"
            )
    return {
        model_file.file_path: _native_metadata(model_file=model_file, metadata=metadata)
        for model_file, metadata in zip(model_files, parsed, strict=True)
        if metadata != UNSUPPORTED_OUTCOME
    }


def _native_metadata(
    *, model_file: DiscoveredSqlModelFile, metadata: NativeHeaderMetadataRow | str
) -> NativeHeaderMetadata:
    columns, audits = ((), ()) if isinstance(metadata, str) else metadata
    return NativeHeaderMetadata(
        raw_columns=model_file.header_values.get(COLUMNS_HEADER_KEY),
        raw_audits=model_file.header_values.get(AUDITS_HEADER_KEY),
        column_locations=model_file.header_column_locations,
        columns=() if isinstance(columns, _native.NativeConfigError) else columns,
        audits=() if audits is None or isinstance(audits, _native.NativeConfigError) else audits,
        columns_error=columns if isinstance(columns, _native.NativeConfigError) else None,
        audits_error=audits if isinstance(audits, _native.NativeConfigError) else None,
    )


def _contract_shapes_match() -> bool:
    return (
        tuple(field.name for field in fields(SchemaColumn)) == SCHEMA_COLUMN_FIELDS
        and tuple(field.name for field in fields(SchemaAuditInstance))
        == SCHEMA_AUDIT_INSTANCE_FIELDS
        and not hasattr(SchemaColumn, "__post_init__")
        and not hasattr(SchemaAuditInstance, "__post_init__")
    )
