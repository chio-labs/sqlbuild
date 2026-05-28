"""Virtual function version helpers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import Any

from sqlbuild.compiler.compile.models.core import FunctionArgument, FunctionReturnColumn
from sqlbuild.compiler.compile.types import FunctionLanguage
from sqlbuild.compiler.planner.models import FunctionPlanEntry
from sqlbuild.virtual.shared.helpers.encoding import decode_state_text, encode_state_text
from sqlbuild.virtual.state.models import FunctionVersionRecord
from sqlbuild.virtual.state.types import ModelVersionStatus


def build_function_version_record(function_entry: FunctionPlanEntry) -> FunctionVersionRecord:
    """Build a state row for one planned function definition."""

    fingerprint_sql: str = function_entry.fingerprint_query_sql
    return FunctionVersionRecord(
        function_name=function_entry.name,
        version_hash=function_version_hash(fingerprint_sql),
        language=function_entry.language.value,
        returns=function_entry.returns,
        arguments_json_b64=encode_state_text(_json_dataclasses(function_entry.arguments)),
        return_columns_json_b64=encode_state_text(_json_dataclasses(function_entry.return_columns)),
        packages_json_b64=encode_state_text(_json_values(function_entry.packages)),
        runtime_version=function_entry.runtime_version,
        entry_point=function_entry.entry_point,
        body_sql_b64=encode_state_text(function_entry.body_sql),
        fingerprint_query_sql_b64=encode_state_text(fingerprint_sql),
        status=ModelVersionStatus.READY,
    )


def function_version_hash(fingerprint_sql: str) -> str:
    """Return the function version hash for fingerprint SQL."""

    return hashlib.sha256(fingerprint_sql.encode("utf-8")).hexdigest()


def decode_function_arguments(record: FunctionVersionRecord) -> tuple[FunctionArgument, ...]:
    """Decode persisted function arguments."""

    values: list[dict[str, object]] = _decode_json_list(record.arguments_json_b64)
    return tuple(
        FunctionArgument(name=str(value["name"]), type=str(value["type"])) for value in values
    )


def decode_function_return_columns(
    record: FunctionVersionRecord,
) -> tuple[FunctionReturnColumn, ...]:
    """Decode persisted table-function return columns."""

    values: list[dict[str, object]] = _decode_json_list(record.return_columns_json_b64)
    return tuple(
        FunctionReturnColumn(name=str(value["name"]), type=str(value["type"])) for value in values
    )


def decode_function_packages(record: FunctionVersionRecord) -> tuple[str, ...]:
    """Decode persisted function packages."""

    values: list[object] = _decode_json_list(record.packages_json_b64)
    return tuple(str(value) for value in values)


def decode_function_body_sql(record: FunctionVersionRecord) -> str:
    """Decode persisted function body SQL."""

    return decode_state_text(record.body_sql_b64) or ""


def decode_function_language(record: FunctionVersionRecord) -> FunctionLanguage:
    """Decode persisted function language."""

    return FunctionLanguage(record.language)


def _json_dataclasses(values: tuple[FunctionArgument | FunctionReturnColumn | object, ...]) -> str:
    encoded: list[dict[str, str]] = []
    for value in values:
        if isinstance(value, FunctionArgument | FunctionReturnColumn):
            encoded.append(asdict(value))
    return _json_values(tuple(encoded))


def _json_values(values: tuple[object, ...]) -> str:
    return json.dumps(values, sort_keys=True, separators=(",", ":"))


def _decode_json_list(value_b64: str) -> list[Any]:
    decoded: str | None = decode_state_text(value_b64)
    if decoded is None:
        return []
    value: object = json.loads(decoded)
    if not isinstance(value, list):
        return []
    return value
