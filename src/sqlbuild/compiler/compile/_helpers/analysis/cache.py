"""Versioned project-local cache for successful model SQL analysis facts."""

from __future__ import annotations

import hashlib
import inspect
import json
import platform
import sqlite3
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, cast

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.compile.exceptions import AnalysisCacheEntryError
from sqlbuild.compiler.compile.models import (
    AnalysisCacheContext,
    CompiledLineageColumnFact,
    CompiledLineageSourceFact,
    CompileSqlReference,
    InferredColumn,
    PolyglotAnalysisResult,
)
from sqlbuild.compiler.lineage.types import (
    ColumnLineageConfidence,
    ColumnTransformKind,
    InferredNullability,
)

_ANALYSIS_CACHE_VERSION: int = 1
_ANALYSIS_ALGORITHM_FINGERPRINT: str = "model-sql-analysis-v1"
_MAX_CACHE_ENTRY_BYTES: int = 10_000_000
_LOCAL_QUALNAME_MARKER: str = "<locals>"
_SQLITE_QUERY_CHUNK_SIZE: int = 500
_SQLITE_TIMEOUT_SECONDS: float = 0.1
_CACHE_DATABASE_NAME: str = "model-analysis.sqlite3"
_CREATE_CACHE_TABLE_SQL: str = """
CREATE TABLE IF NOT EXISTS model_analysis (
    cache_key TEXT PRIMARY KEY,
    payload TEXT NOT NULL
)
"""


def build_analysis_cache_context(
    *,
    root: Path | None,
    inference_profile: ExpressionInferenceProfile,
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
    column_types_by_table: dict[str, dict[str, str]],
    allow_compact_analysis: bool,
) -> AnalysisCacheContext | None:
    """Build a reusable cache context, or bypass when profile identity is unstable."""

    if root is None:
        return None
    profile_payload: dict[str, object] | None = _inference_profile_payload(inference_profile)
    if profile_payload is None:
        return None
    shared_payload: dict[str, object] = {
        "algorithm": _ANALYSIS_ALGORITHM_FINGERPRINT,
        "cache_version": _ANALYSIS_CACHE_VERSION,
        "sqlbuild_version": _package_version("sqlbuild"),
        "polyglot_version": _package_version("polyglot-sql"),
        "python_version": platform.python_version_tuple()[:2],
        "allow_compact_analysis": allow_compact_analysis,
        "inference_profile": profile_payload,
        "column_nullability_by_table": _nullability_payload(column_nullability_by_table),
        "column_types_by_table": {
            table: dict(sorted(columns.items()))
            for table, columns in sorted(column_types_by_table.items())
        },
    }
    return AnalysisCacheContext(
        root=root,
        shared_fingerprint=_payload_digest(shared_payload),
    )


def model_analysis_cache_key(
    *,
    context: AnalysisCacheContext,
    query_sql: str,
    references: tuple[CompileSqlReference, ...],
    placeholders: dict[str, str] | None,
) -> str:
    """Return the exact analysis identity for one expanded model query."""

    return _payload_digest(
        {
            "shared_fingerprint": context.shared_fingerprint,
            "query_sql": query_sql,
            "references": [
                {
                    "kind": str(reference.ref_kind),
                    "name": reference.ref_name,
                    "package": reference.ref_package,
                    "call_argument_count": reference.call_argument_count,
                }
                for reference in references
            ],
            "placeholders": dict(sorted((placeholders or {}).items())),
        }
    )


def read_model_analyses(
    *,
    context: AnalysisCacheContext,
    cache_keys: tuple[str, ...],
) -> dict[str, PolyglotAnalysisResult]:
    """Read cached analyses in batches, treating invalid entries or storage as misses."""

    database_path: Path = _cache_database_path(context=context)
    if not database_path.is_file() or not cache_keys:
        return {}
    analyses: dict[str, PolyglotAnalysisResult] = {}
    try:
        connection_uri: str = f"file:{database_path}?mode=ro"
        with sqlite3.connect(
            connection_uri,
            uri=True,
            timeout=_SQLITE_TIMEOUT_SECONDS,
        ) as connection:
            for start in range(0, len(cache_keys), _SQLITE_QUERY_CHUNK_SIZE):
                chunk: tuple[str, ...] = cache_keys[start : start + _SQLITE_QUERY_CHUNK_SIZE]
                placeholders: str = ",".join("?" for _ in chunk)
                rows: list[tuple[str, str]] = connection.execute(
                    f"SELECT cache_key, payload FROM model_analysis "
                    f"WHERE cache_key IN ({placeholders})",
                    chunk,
                ).fetchall()
                for cache_key, contents in rows:
                    analysis: PolyglotAnalysisResult | None = _analysis_from_contents(
                        contents=contents,
                        expected_cache_key=cache_key,
                    )
                    if analysis is not None:
                        analyses[cache_key] = analysis
    except (OSError, sqlite3.DatabaseError):
        return {}
    return analyses


def write_model_analyses(
    *,
    context: AnalysisCacheContext,
    analyses_by_key: dict[str, PolyglotAnalysisResult],
) -> None:
    """Transactionally persist successful analyses; cache failures never fail compilation."""

    rows: list[tuple[str, str]] = [
        (
            cache_key,
            json.dumps(
                _analysis_payload(cache_key=cache_key, analysis=analysis),
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
        )
        for cache_key, analysis in analyses_by_key.items()
        if analysis.analysis_succeeded
    ]
    if not rows:
        return
    try:
        database_path: Path = _cache_database_path(context=context)
        database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(database_path, timeout=_SQLITE_TIMEOUT_SECONDS) as connection:
            _ = connection.execute(_CREATE_CACHE_TABLE_SQL)
            _ = connection.executemany(
                "INSERT OR REPLACE INTO model_analysis (cache_key, payload) VALUES (?, ?)",
                rows,
            )
    except (OSError, sqlite3.DatabaseError):
        return


def _analysis_from_contents(
    *, contents: str, expected_cache_key: str
) -> PolyglotAnalysisResult | None:
    if len(contents.encode("utf-8")) > _MAX_CACHE_ENTRY_BYTES:
        return None
    try:
        payload: object = json.loads(contents)
        return _analysis_from_payload(payload=payload, expected_cache_key=expected_cache_key)
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None


def _inference_profile_payload(
    profile: ExpressionInferenceProfile,
) -> dict[str, object] | None:
    rules: list[dict[str, str]] = []
    for name, rule in sorted(profile.function_nullability_rules.items()):
        if not inspect.isfunction(rule):
            return None
        module: str = rule.__module__
        qualname: str = rule.__qualname__
        if (
            not module.startswith("sqlbuild.")
            or _LOCAL_QUALNAME_MARKER in qualname
            or rule.__closure__ is not None
            or rule.__defaults__ is not None
            or rule.__kwdefaults__ is not None
        ):
            return None
        try:
            source: str = inspect.getsource(rule)
        except (OSError, TypeError):
            return None
        rules.append(
            {
                "name": name,
                "module": module,
                "qualname": qualname,
                "source_digest": hashlib.sha256(source.encode("utf-8")).hexdigest(),
            }
        )
    return {
        "sql_analysis_dialect": profile.sql_analysis_dialect,
        "function_nullability_rules": rules,
    }


def _nullability_payload(
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
) -> dict[str, dict[str, str]]:
    payload: dict[str, dict[str, str]] = {}
    for table, columns in sorted(column_nullability_by_table.items()):
        payload[table] = {
            column: nullability.value for column, nullability in sorted(columns.items())
        }
    return payload


def _analysis_payload(
    *, cache_key: str, analysis: PolyglotAnalysisResult
) -> dict[str, object]:
    analysis_payload: dict[str, object] = {
        "columns": (
            None
            if analysis.columns is None
            else [
                {
                    "name": column.name,
                    "type": column.type,
                    "nullability": column.nullability.value,
                }
                for column in analysis.columns
            ]
        ),
        "lineage_columns": [
            _lineage_column_payload(column) for column in analysis.lineage_columns
        ],
        "has_star": analysis.has_star,
    }
    return {
        "version": _ANALYSIS_CACHE_VERSION,
        "cache_key": cache_key,
        "analysis_succeeded": True,
        "analysis_digest": _payload_digest(analysis_payload),
        "analysis": analysis_payload,
    }


def _lineage_column_payload(column: CompiledLineageColumnFact) -> dict[str, object]:
    return {
        "output_column": column.output_column,
        "transform_kind": column.transform_kind.value,
        "confidence": column.confidence.value,
        "upstream_columns": [
            {
                "resource_type": str(source.resource_type),
                "resource_name": source.resource_name,
                "column_name": source.column_name,
            }
            for source in column.upstream_columns
        ],
    }


def _analysis_from_payload(
    *, payload: object, expected_cache_key: str
) -> PolyglotAnalysisResult:
    if not isinstance(payload, dict):
        raise AnalysisCacheEntryError("analysis cache entry must be an object")
    values: dict[str, Any] = cast(dict[str, Any], payload)
    version_value: object = values["version"]
    if type(version_value) is not int or version_value != _ANALYSIS_CACHE_VERSION:
        raise AnalysisCacheEntryError("analysis cache version mismatch")
    if values["cache_key"] != expected_cache_key:
        raise AnalysisCacheEntryError("analysis cache key mismatch")
    if values["analysis_succeeded"] is not True:
        raise AnalysisCacheEntryError("analysis cache contains an unsuccessful result")
    analysis_payload: object = values["analysis"]
    if not isinstance(analysis_payload, dict):
        raise AnalysisCacheEntryError("analysis cache facts must be an object")
    if values["analysis_digest"] != _payload_digest(analysis_payload):
        raise AnalysisCacheEntryError("analysis cache facts checksum mismatch")
    analysis_values: dict[str, Any] = cast(dict[str, Any], analysis_payload)
    columns_payload: object = analysis_values["columns"]
    columns: tuple[InferredColumn, ...] | None = (
        None
        if columns_payload is None
        else tuple(
            InferredColumn(
                name=str(column["name"]),
                type=None if column.get("type") is None else str(column["type"]),
                nullability=InferredNullability(str(column["nullability"])),
            )
            for column in _object_list(columns_payload)
        )
    )
    lineage_columns: tuple[CompiledLineageColumnFact, ...] = tuple(
        _lineage_column_from_payload(column)
        for column in _object_list(analysis_values["lineage_columns"])
    )
    has_star: object = analysis_values["has_star"]
    if not isinstance(has_star, bool):
        raise AnalysisCacheEntryError("analysis cache has_star must be a boolean")
    return PolyglotAnalysisResult(
        analysis_succeeded=True,
        columns=columns,
        lineage_columns=lineage_columns,
        has_star=has_star,
    )


def _object_list(payload: object) -> list[dict[str, Any]]:
    if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
        raise AnalysisCacheEntryError("analysis cache collection must contain objects")
    return cast(list[dict[str, Any]], payload)


def _lineage_column_from_payload(payload: dict[str, Any]) -> CompiledLineageColumnFact:
    return CompiledLineageColumnFact(
        output_column=str(payload["output_column"]),
        transform_kind=ColumnTransformKind(str(payload["transform_kind"])),
        confidence=ColumnLineageConfidence(str(payload["confidence"])),
        upstream_columns=tuple(
            CompiledLineageSourceFact(
                resource_type=str(source["resource_type"]),
                resource_name=str(source["resource_name"]),
                column_name=str(source["column_name"]),
            )
            for source in _object_list(payload["upstream_columns"])
        ),
    )


def _cache_database_path(*, context: AnalysisCacheContext) -> Path:
    return context.root / f"v{_ANALYSIS_CACHE_VERSION}" / _CACHE_DATABASE_NAME


def _payload_digest(payload: object) -> str:
    encoded: bytes = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _package_version(package: str) -> str:
    try:
        return version(package)
    except PackageNotFoundError:
        return "unknown"
