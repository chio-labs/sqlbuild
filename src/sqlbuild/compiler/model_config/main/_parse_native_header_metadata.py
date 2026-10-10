"""Parse a MODEL header's columns and audits natively."""

from __future__ import annotations

from pathlib import Path

import sqlbuild._native as _native
from sqlbuild.compiler.model_config.main._native_contract_classes import native_contract_classes
from sqlbuild.compiler.model_config.models import NativeHeaderMetadata
from sqlbuild.compiler.model_config.types import NativeHeaderMetadataRow
from sqlbuild.spec.contracts.models import SourceLocation


def parse_native_header_metadata(
    *,
    raw_columns: object | None,
    raw_audits: object | None,
    column_locations: dict[str, SourceLocation],
    file_path: Path,
) -> NativeHeaderMetadata:
    """Return one model's header columns and audits, or the error each raises."""

    row: NativeHeaderMetadataRow = _native.parse_model_header_metadata(
        (raw_columns, raw_audits), (column_locations, str(file_path)), native_contract_classes()
    )
    columns, audits = row
    return NativeHeaderMetadata(
        columns=() if isinstance(columns, _native.NativeConfigError) else columns,
        audits=() if audits is None or isinstance(audits, _native.NativeConfigError) else audits,
        columns_error=columns if isinstance(columns, _native.NativeConfigError) else None,
        audits_error=audits if isinstance(audits, _native.NativeConfigError) else None,
    )
