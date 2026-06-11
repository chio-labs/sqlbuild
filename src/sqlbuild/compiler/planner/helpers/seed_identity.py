"""Stable seed identity helpers for standard changes-only planning."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from sqlbuild.compiler.compile.models.core import CompiledSeed
from sqlbuild.compiler.planner.helpers.version_identity_hashing import stable_version_identity_hash
from sqlbuild.spec.models.schema import SchemaColumn, SeedCsvSettings


def build_seed_identity(seed: CompiledSeed) -> tuple[str, str]:
    """Return ``(identity_hash, metadata_json)`` for one compiled seed."""

    metadata_json: str = build_seed_identity_metadata_json(seed)
    return stable_version_identity_hash(metadata_json), metadata_json


def build_seed_identity_metadata_json(seed: CompiledSeed) -> str:
    """Build deterministic seed identity metadata from content and load-affecting config."""

    payload: dict[str, object] = {
        "name": seed.name,
        "csv_settings": _normalize_json_value(asdict(seed.schema_entry.csv_settings)),
        "columns": [_column_identity(column) for column in seed.schema_entry.columns],
        "rows": _read_seed_rows(
            file_path=seed.seed_file.file_path,
            csv_settings=seed.schema_entry.csv_settings,
        ),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _read_seed_rows(*, file_path: Path, csv_settings: SeedCsvSettings) -> list[list[str]]:
    encoding: str = csv_settings.encoding or "utf-8-sig"
    dialect_options: dict[str, Any] = {}
    if csv_settings.delimiter is not None:
        dialect_options["delimiter"] = csv_settings.delimiter
    if csv_settings.quotechar is not None:
        dialect_options["quotechar"] = csv_settings.quotechar
    if csv_settings.doublequote is not None:
        dialect_options["doublequote"] = csv_settings.doublequote
    if csv_settings.escapechar is not None:
        dialect_options["escapechar"] = csv_settings.escapechar
    if csv_settings.skipinitialspace is not None:
        dialect_options["skipinitialspace"] = csv_settings.skipinitialspace

    rows: list[list[str]] = []
    with file_path.open("r", encoding=encoding, newline="") as handle:
        reader: Any = csv.reader(handle, **dialect_options)
        for row in reader:
            rows.append(list(row))
    return rows


def _column_identity(column: SchemaColumn) -> dict[str, object]:
    return {
        "name": column.name,
        "type": column.type,
        "nullable": column.nullable,
    }


def _normalize_json_value(value: object) -> object:
    if isinstance(value, dict):
        return {str(k): _normalize_json_value(v) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_normalize_json_value(v) for v in value]
    return value
