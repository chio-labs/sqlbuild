"""Versioned project-local cache for successful model SQL analysis facts."""

from __future__ import annotations

import hashlib
import hmac
import inspect
import json
import platform
import sqlite3
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from string import hexdigits
from typing import Any, cast

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.compile._helpers.analysis.columns import table_function_analysis_name
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
from sqlbuild.compiler.references.types import SqlReferenceKind

_ANALYSIS_CACHE_VERSION: int = 4
_ANALYSIS_ALGORITHM_FINGERPRINT: str = "model-sql-analysis-v4"
_MAX_CACHE_ENTRY_BYTES: int = 10_000_000
_SHA256_HEX_LENGTH: int = 64
_CACHE_ENTRY_SEPARATOR: str = "\n"
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
_CREATE_SIGNATURE_TABLE_SQL: str = """
CREATE TABLE IF NOT EXISTS model_analysis_signature (
    shared_fingerprint TEXT NOT NULL,
    signature_namespace TEXT NOT NULL,
    model_name TEXT NOT NULL,
    output_signature TEXT NOT NULL,
    PRIMARY KEY (shared_fingerprint, signature_namespace, model_name)
)
"""
_CREATE_DEPENDENCY_TABLE_SQL: str = """
CREATE TABLE IF NOT EXISTS model_analysis_dependency (
    signature_namespace TEXT NOT NULL,
    cache_key TEXT NOT NULL,
    upstream_model_name TEXT NOT NULL,
    output_signature TEXT NOT NULL,
    PRIMARY KEY (signature_namespace, cache_key, upstream_model_name)
)
"""


def build_analysis_cache_context(
    *,
    root: Path | None,
    inference_profile: ExpressionInferenceProfile,
    allow_compact_analysis: bool,
    signature_namespace: object = None,
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
    }
    try:
        return AnalysisCacheContext(
            root=root,
            shared_fingerprint=_payload_digest(shared_payload),
            signature_namespace=_payload_digest(signature_namespace),
        )
    except (TypeError, ValueError):
        return None


def model_analysis_cache_key(
    *,
    context: AnalysisCacheContext,
    query_sql: str,
    references: tuple[CompileSqlReference, ...],
    placeholders: dict[str, str] | None,
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
    column_types_by_table: dict[str, dict[str, str]],
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
            "referenced_column_nullability": _referenced_nullability_payload(
                references=references,
                column_nullability_by_table=column_nullability_by_table,
            ),
            "referenced_column_types": _referenced_types_payload(
                references=references,
                column_types_by_table=column_types_by_table,
            ),
        }
    )


def read_model_analyses(
    *,
    context: AnalysisCacheContext,
    cache_keys: tuple[str, ...],
    model_names: tuple[str, ...],
    upstream_model_names_by_key: dict[str, tuple[str, ...]],
) -> tuple[dict[str, PolyglotAnalysisResult], dict[str, str], dict[str, str]]:
    """Read one consistent snapshot of analyses, dependencies, and output signatures."""

    database_path: Path = _cache_database_path(context=context)
    if not database_path.is_file() or not cache_keys:
        return {}, {}, {}
    analyses: dict[str, PolyglotAnalysisResult] = {}
    signatures: dict[str, str] = {}
    output_signatures_by_key: dict[str, str] = {}
    try:
        connection_uri: str = f"file:{database_path}?mode=ro"
        with sqlite3.connect(
            connection_uri,
            uri=True,
            timeout=_SQLITE_TIMEOUT_SECONDS,
        ) as connection:
            _ = connection.execute("BEGIN")
            signature_model_name_set: set[str] = set(model_names)
            upstream_names: tuple[str, ...]
            for upstream_names in upstream_model_names_by_key.values():
                signature_model_name_set.update(upstream_names)
            signature_model_names: tuple[str, ...] = tuple(sorted(signature_model_name_set))
            for start in range(0, len(signature_model_names), _SQLITE_QUERY_CHUNK_SIZE):
                model_chunk: tuple[str, ...] = signature_model_names[
                    start : start + _SQLITE_QUERY_CHUNK_SIZE
                ]
                model_placeholders: str = ",".join("?" for _ in model_chunk)
                signature_rows: list[tuple[str, str]] = connection.execute(
                    f"SELECT model_name, output_signature FROM model_analysis_signature "
                    f"WHERE shared_fingerprint = ? AND signature_namespace = ? "
                    f"AND model_name IN ({model_placeholders})",
                    (
                        context.shared_fingerprint,
                        context.signature_namespace,
                        *model_chunk,
                    ),
                ).fetchall()
                signatures.update(signature_rows)
            for start in range(0, len(cache_keys), _SQLITE_QUERY_CHUNK_SIZE):
                chunk: tuple[str, ...] = cache_keys[start : start + _SQLITE_QUERY_CHUNK_SIZE]
                placeholders: str = ",".join("?" for _ in chunk)
                rows: list[tuple[str, str]] = connection.execute(
                    f"SELECT cache_key, payload FROM model_analysis "
                    f"WHERE cache_key IN ({placeholders})",
                    chunk,
                ).fetchall()
                dependency_rows: list[tuple[str, str, str]] = connection.execute(
                    f"SELECT cache_key, upstream_model_name, output_signature "
                    f"FROM model_analysis_dependency WHERE signature_namespace = ? "
                    f"AND cache_key IN ({placeholders})",
                    (context.signature_namespace, *chunk),
                ).fetchall()
                dependencies_by_key: dict[str, dict[str, str]] = {}
                for cache_key, upstream_name, output_signature in dependency_rows:
                    dependencies_by_key.setdefault(cache_key, {})[upstream_name] = output_signature
                for cache_key, contents in rows:
                    expected_dependencies: dict[str, str] | None = _expected_dependencies(
                        upstream_model_names=upstream_model_names_by_key.get(cache_key, ()),
                        signatures=signatures,
                    )
                    if (
                        expected_dependencies is None
                        or dependencies_by_key.get(cache_key, {}) != expected_dependencies
                    ):
                        continue
                    cached_result: tuple[PolyglotAnalysisResult, str] | None = (
                        _analysis_from_contents(
                            contents=contents,
                            expected_cache_key=cache_key,
                        )
                    )
                    if cached_result is not None:
                        analysis, output_signature = cached_result
                        analyses[cache_key] = analysis
                        output_signatures_by_key[cache_key] = output_signature
    except (OSError, sqlite3.DatabaseError):
        return {}, {}, {}
    return analyses, signatures, output_signatures_by_key


def write_model_analyses(
    *,
    context: AnalysisCacheContext,
    analyses_by_key: dict[str, PolyglotAnalysisResult],
    latest_analyses_by_model: dict[str, PolyglotAnalysisResult] | None = None,
    dependency_signatures_by_key: dict[str, dict[str, str]] | None = None,
) -> None:
    """Transactionally persist successful analyses; cache failures never fail compilation."""

    rows: list[tuple[str, str]] = [
        (
            cache_key,
            _analysis_contents(cache_key=cache_key, analysis=analysis),
        )
        for cache_key, analysis in analyses_by_key.items()
        if analysis.analysis_succeeded
    ]
    signature_rows: list[tuple[str, str, str, str]] = [
        (
            context.shared_fingerprint,
            context.signature_namespace,
            model_name,
            model_analysis_output_signature(analysis),
        )
        for model_name, analysis in (latest_analyses_by_model or {}).items()
        if analysis.analysis_succeeded
    ]
    dependency_rows: list[tuple[str, str, str, str]] = []
    for cache_key, dependencies in (dependency_signatures_by_key or {}).items():
        analysis: PolyglotAnalysisResult | None = analyses_by_key.get(cache_key)
        if analysis is None or not analysis.analysis_succeeded:
            continue
        dependency_rows.extend(
            (context.signature_namespace, cache_key, upstream_name, output_signature)
            for upstream_name, output_signature in dependencies.items()
        )
    if not rows and not signature_rows:
        return
    try:
        database_path: Path = _cache_database_path(context=context)
        database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(database_path, timeout=_SQLITE_TIMEOUT_SECONDS) as connection:
            _ = connection.execute(_CREATE_CACHE_TABLE_SQL)
            _ = connection.execute(_CREATE_SIGNATURE_TABLE_SQL)
            _ = connection.execute(_CREATE_DEPENDENCY_TABLE_SQL)
            _ = connection.executemany(
                "INSERT OR REPLACE INTO model_analysis (cache_key, payload) VALUES (?, ?)",
                rows,
            )
            written_cache_keys: tuple[str, ...] = tuple(cache_key for cache_key, _ in rows)
            for start in range(0, len(written_cache_keys), _SQLITE_QUERY_CHUNK_SIZE):
                chunk: tuple[str, ...] = written_cache_keys[
                    start : start + _SQLITE_QUERY_CHUNK_SIZE
                ]
                placeholders: str = ",".join("?" for _ in chunk)
                _ = connection.execute(
                    f"DELETE FROM model_analysis_dependency "
                    f"WHERE signature_namespace = ? AND cache_key IN ({placeholders})",
                    (context.signature_namespace, *chunk),
                )
            _ = connection.executemany(
                "INSERT INTO model_analysis_dependency "
                "(signature_namespace, cache_key, upstream_model_name, output_signature) "
                "VALUES (?, ?, ?, ?)",
                dependency_rows,
            )
            _ = connection.executemany(
                "INSERT OR REPLACE INTO model_analysis_signature "
                "(shared_fingerprint, signature_namespace, model_name, output_signature) "
                "VALUES (?, ?, ?, ?)",
                signature_rows,
            )
    except (OSError, sqlite3.DatabaseError):
        return


def _expected_dependencies(
    *,
    upstream_model_names: tuple[str, ...],
    signatures: dict[str, str],
) -> dict[str, str] | None:
    if any(name not in signatures for name in upstream_model_names):
        return None
    return {name: signatures[name] for name in upstream_model_names}


def model_analysis_output_signature(analysis: PolyglotAnalysisResult) -> str:
    """Return the exported column signature relevant to downstream analysis."""

    return _payload_digest(
        {
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
            "has_star": analysis.has_star,
        }
    )


def _analysis_from_contents(
    *, contents: str, expected_cache_key: str
) -> tuple[PolyglotAnalysisResult, str] | None:
    encoded_contents: bytes = contents.encode("utf-8")
    if len(encoded_contents) > _MAX_CACHE_ENTRY_BYTES:
        return None
    try:
        stored_digest, separator, serialized_payload = contents.partition(_CACHE_ENTRY_SEPARATOR)
        if not separator or not hmac.compare_digest(
            stored_digest,
            _cache_entry_digest(
                cache_key=expected_cache_key,
                serialized_payload=serialized_payload,
            ),
        ):
            return None
        payload: object = json.loads(serialized_payload)
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


def _referenced_nullability_payload(
    *,
    references: tuple[CompileSqlReference, ...],
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
) -> dict[str, dict[str, str]]:
    payload: dict[str, dict[str, str]] = {}
    table: str
    for table in _referenced_analysis_tables(references):
        columns: dict[str, InferredNullability] | None = column_nullability_by_table.get(table)
        if columns is None:
            continue
        payload[table] = {
            column: nullability.value for column, nullability in sorted(columns.items())
        }
    return payload


def _referenced_types_payload(
    *,
    references: tuple[CompileSqlReference, ...],
    column_types_by_table: dict[str, dict[str, str]],
) -> dict[str, dict[str, str]]:
    payload: dict[str, dict[str, str]] = {}
    table: str
    for table in _referenced_analysis_tables(references):
        columns: dict[str, str] | None = column_types_by_table.get(table)
        if columns is not None:
            payload[table] = dict(sorted(columns.items()))
    return payload


def _referenced_analysis_tables(
    references: tuple[CompileSqlReference, ...],
) -> tuple[str, ...]:
    names: set[str] = set()
    for reference in references:
        names.add(
            table_function_analysis_name(reference.ref_name)
            if reference.ref_kind == SqlReferenceKind.TABLE_FUNCTION
            else reference.ref_name
        )
    return tuple(sorted(names))


def _analysis_payload(*, cache_key: str, analysis: PolyglotAnalysisResult) -> dict[str, object]:
    return {
        "v": _ANALYSIS_CACHE_VERSION,
        "k": cache_key,
        "s": model_analysis_output_signature(analysis),
        "c": (
            None
            if analysis.columns is None
            else [
                [column.name, column.type, column.nullability.value] for column in analysis.columns
            ]
        ),
        "l": [_lineage_column_payload(column) for column in analysis.lineage_columns],
        "h": analysis.has_star,
    }


def _lineage_column_payload(column: CompiledLineageColumnFact) -> list[object]:
    return [
        column.output_column,
        column.transform_kind.value,
        column.confidence.value,
        [
            [
                str(source.resource_type),
                source.resource_name,
                source.column_name,
            ]
            for source in column.upstream_columns
        ],
    ]


def _analysis_from_payload(
    *, payload: object, expected_cache_key: str
) -> tuple[PolyglotAnalysisResult, str]:
    if not isinstance(payload, dict):
        raise AnalysisCacheEntryError("analysis cache entry must be an object")
    values: dict[str, Any] = cast(dict[str, Any], payload)
    version_value: object = values["v"]
    if type(version_value) is not int or version_value != _ANALYSIS_CACHE_VERSION:
        raise AnalysisCacheEntryError("analysis cache version mismatch")
    if values["k"] != expected_cache_key:
        raise AnalysisCacheEntryError("analysis cache key mismatch")
    output_signature: object = values["s"]
    if not (
        isinstance(output_signature, str)
        and len(output_signature) == _SHA256_HEX_LENGTH
        and all(character in hexdigits for character in output_signature)
    ):
        raise AnalysisCacheEntryError("analysis cache output signature is invalid")
    columns_payload: object = values["c"]
    columns: tuple[InferredColumn, ...] | None = (
        None
        if columns_payload is None
        else tuple(_column_from_payload(column) for column in _value_lists(columns_payload))
    )
    lineage_columns: tuple[CompiledLineageColumnFact, ...] = tuple(
        _lineage_column_from_payload(column) for column in _value_lists(values["l"])
    )
    has_star: object = values["h"]
    if not isinstance(has_star, bool):
        raise AnalysisCacheEntryError("analysis cache has_star must be a boolean")
    return (
        PolyglotAnalysisResult(
            analysis_succeeded=True,
            columns=columns,
            lineage_columns=lineage_columns,
            has_star=has_star,
        ),
        output_signature,
    )


def _value_lists(payload: object) -> list[list[object]]:
    if not isinstance(payload, list) or not all(isinstance(item, list) for item in payload):
        raise AnalysisCacheEntryError("analysis cache collection must contain arrays")
    return cast(list[list[object]], payload)


def _column_from_payload(payload: list[object]) -> InferredColumn:
    column_value_count: int = 3
    if len(payload) != column_value_count:
        raise AnalysisCacheEntryError("analysis cache column must contain three values")
    name, column_type, nullability = payload
    if not isinstance(name, str) or not isinstance(nullability, str):
        raise AnalysisCacheEntryError("analysis cache column name and nullability must be strings")
    if column_type is not None and not isinstance(column_type, str):
        raise AnalysisCacheEntryError("analysis cache column type must be a string or null")
    return InferredColumn(
        name=name,
        type=column_type,
        nullability=InferredNullability(nullability),
    )


def _lineage_column_from_payload(payload: list[object]) -> CompiledLineageColumnFact:
    lineage_value_count: int = 4
    if len(payload) != lineage_value_count:
        raise AnalysisCacheEntryError("analysis cache lineage column must contain four values")
    output_column, transform_kind, confidence, upstream_columns = payload
    if not all(isinstance(value, str) for value in (output_column, transform_kind, confidence)):
        raise AnalysisCacheEntryError("analysis cache lineage attributes must be strings")
    return CompiledLineageColumnFact(
        output_column=cast(str, output_column),
        transform_kind=ColumnTransformKind(cast(str, transform_kind)),
        confidence=ColumnLineageConfidence(cast(str, confidence)),
        upstream_columns=tuple(
            _lineage_source_from_payload(source) for source in _value_lists(upstream_columns)
        ),
    )


def _lineage_source_from_payload(payload: list[object]) -> CompiledLineageSourceFact:
    source_value_count: int = 3
    if len(payload) != source_value_count or not all(isinstance(value, str) for value in payload):
        raise AnalysisCacheEntryError("analysis cache lineage source must contain three strings")
    resource_type, resource_name, column_name = cast(list[str], payload)
    return CompiledLineageSourceFact(
        resource_type=resource_type,
        resource_name=resource_name,
        column_name=column_name,
    )


def _cache_database_path(*, context: AnalysisCacheContext) -> Path:
    return context.root / f"v{_ANALYSIS_CACHE_VERSION}" / _CACHE_DATABASE_NAME


def _analysis_contents(*, cache_key: str, analysis: PolyglotAnalysisResult) -> str:
    serialized_payload: str = json.dumps(
        _analysis_payload(cache_key=cache_key, analysis=analysis),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return _CACHE_ENTRY_SEPARATOR.join(
        (
            _cache_entry_digest(cache_key=cache_key, serialized_payload=serialized_payload),
            serialized_payload,
        )
    )


def _cache_entry_digest(*, cache_key: str, serialized_payload: str) -> str:
    encoded: bytes = f"{cache_key}\0{serialized_payload}".encode()
    return hashlib.sha256(encoded).hexdigest()


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
