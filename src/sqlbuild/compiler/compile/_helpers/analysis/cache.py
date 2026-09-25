"""Versioned project-local cache for deterministic model SQL analysis facts."""

from __future__ import annotations

import hashlib
import hmac
import inspect
import json
import platform
import sqlite3
import time
from collections import defaultdict, deque
from collections.abc import Sequence
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from string import hexdigits
from typing import Any, cast

import orjson

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.compile._helpers.analysis.columns import table_function_analysis_name
from sqlbuild.compiler.compile.exceptions import AnalysisCacheEntryError
from sqlbuild.compiler.compile.models import (
    AnalysisCacheContext,
    CompactAnalysisCacheCandidate,
    CompactAnalysisCacheModel,
    CompactAnalysisCachePlan,
    CompactBatchPreparation,
    CompactLineageFacts,
    CompiledLineageColumnFact,
    CompiledLineageSourceFact,
    CompileSqlReference,
    InferredColumn,
    PolyglotAnalysisResult,
)
from sqlbuild.compiler.compile.types import CompactBatchResponseCallback, CompiledResourceType
from sqlbuild.compiler.lineage.types import (
    ColumnLineageConfidence,
    ColumnTransformKind,
    InferredNullability,
)
from sqlbuild.compiler.profiling.main._metric import record_compile_metric
from sqlbuild.compiler.profiling.main.record import record_compile_timing
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.compiler.sql_analysis.constants import BINDING_SEVERITIES, TYPE_CHECKED_DIALECTS
from sqlbuild.compiler.sql_analysis.models import SqlBindingDiagnostic

_ANALYSIS_CACHE_VERSION: int = 12
_ANALYSIS_ALGORITHM_FINGERPRINT: str = "model-sql-analysis-v15-semantic-types"
_LINEAGE_COLUMN_VALUE_COUNT: int = 4
_LINEAGE_SOURCE_VALUE_COUNT: int = 3
_COMPACT_TRANSFORM_CODES: dict[str, int] = {
    CompactLineageFacts.transform_kind(code).value: code for code in range(6)
}
_COMPACT_CONFIDENCE_CODES: dict[str, int] = {
    CompactLineageFacts.confidence(code).value: code for code in range(3)
}
_RESOURCE_TYPE_VALUES: frozenset[str] = frozenset(item.value for item in CompiledResourceType)
_NULLABILITY_BY_VALUE: dict[str, InferredNullability] = {
    item.value: item for item in InferredNullability
}
_MAX_CACHE_ENTRY_BYTES: int = 10_000_000
_SHA256_HEX_LENGTH: int = 64
_CACHE_ENTRY_SEPARATOR: str = "\n"
_LOCAL_QUALNAME_MARKER: str = "<locals>"
_SQLITE_QUERY_CHUNK_SIZE: int = 500
_SQLITE_TIMEOUT_SECONDS: float = 0.1
_CACHE_DATABASE_NAME: str = "model-analysis.sqlite3"
_COMPACT_BATCH_CACHE_VERSION: int = 1
_MAX_COMPACT_BATCH_BYTES: int = 128 * 1024 * 1024
_MAX_COMPACT_BATCH_RECORDS: int = 2
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
_CREATE_COMPACT_BATCH_TABLE_SQL: str = """
CREATE TABLE IF NOT EXISTS model_analysis_compact_batch (
    batch_key TEXT PRIMARY KEY,
    shared_fingerprint TEXT NOT NULL,
    payload BLOB NOT NULL,
    created_ns INTEGER NOT NULL
)
"""


def build_analysis_cache_context(
    *,
    root: Path | None,
    inference_profile: ExpressionInferenceProfile,
    allow_compact_analysis: bool,
    rich_type_inference: bool = True,
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
        "polyglot_version": _package_version("polyglot-sql-chio"),
        "python_version": platform.python_version_tuple()[:2],
        "allow_compact_analysis": allow_compact_analysis,
        "rich_type_inference": rich_type_inference,
        "type_checked_dialects": sorted(TYPE_CHECKED_DIALECTS),
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
    binding_schema: dict[str, dict[str, str]] | None = None,
    recover_cte_facts: bool = False,
) -> str:
    """Return the exact analysis identity for one expanded model query."""

    payload: dict[str, object] = {
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
        "binding_schema": binding_schema,
    }
    if recover_cte_facts:
        payload["recover_cte_facts"] = True
    return _json_value_digest(payload)


def compact_analysis_batch_cache_key(
    *, context: AnalysisCacheContext, reuse_keys: tuple[str, ...]
) -> str:
    """Return the exact identity of one ordered whole-project compact analysis batch."""

    return _payload_digest(
        {
            "cache_version": _ANALYSIS_CACHE_VERSION,
            "compact_batch_version": _COMPACT_BATCH_CACHE_VERSION,
            "shared_fingerprint": context.shared_fingerprint,
            "reuse_keys": reuse_keys,
        }
    )


def compact_analysis_model_reuse_key(
    *, cache_key: str, upstream_reuse_keys: tuple[tuple[str, str], ...]
) -> str:
    """Return one model key that changes with every transitive model dependency."""

    return _json_value_digest(
        {
            "cache_key": cache_key,
            "upstream": upstream_reuse_keys,
        }
    )


def build_compact_analysis_cache_plan(
    *,
    context: AnalysisCacheContext | None,
    models: tuple[CompactAnalysisCacheModel, ...],
    min_model_count: int,
) -> CompactAnalysisCachePlan | None:
    """Build a dependency-aware ordered batch identity when every model is cacheable."""

    if context is None or len(models) < min_model_count:
        return None
    models_by_name: dict[str, CompactAnalysisCacheModel] = {model.name: model for model in models}
    dependencies_by_name: dict[str, tuple[str, ...]] = {}
    for model in models:
        dependencies_by_name[model.name] = tuple(
            name for name in model.upstream_names if name in models_by_name
        )
    dependents_by_name: dict[str, list[str]] = defaultdict(list)
    remaining_dependency_count: dict[str, int] = {}
    for model_name, dependencies in dependencies_by_name.items():
        remaining_dependency_count[model_name] = len(dependencies)
        for dependency in dependencies:
            dependents_by_name[dependency].append(model_name)
    resolved: dict[str, str] = {}
    ready: deque[str] = deque(
        sorted(name for name, count in remaining_dependency_count.items() if count == 0)
    )
    while ready:
        model_name: str = ready.popleft()
        model: CompactAnalysisCacheModel = models_by_name[model_name]
        if model.cache_key is None:
            return None
        resolved[model_name] = compact_analysis_model_reuse_key(
            cache_key=model.cache_key,
            upstream_reuse_keys=tuple(
                (upstream_name, resolved[upstream_name])
                for upstream_name in dependencies_by_name[model_name]
            ),
        )
        for dependent_name in sorted(dependents_by_name.get(model_name, ())):
            remaining_dependency_count[dependent_name] -= 1
            if remaining_dependency_count[dependent_name] == 0:
                ready.append(dependent_name)
    if len(resolved) != len(models):
        return None
    cache_keys: tuple[str, ...] = tuple(
        model.cache_key for model in models if model.cache_key is not None
    )
    if len(cache_keys) != len(models):
        return None
    reuse_keys: tuple[str, ...] = tuple(resolved[model.name] for model in models)
    return CompactAnalysisCachePlan(
        context=context,
        batch_key=compact_analysis_batch_cache_key(context=context, reuse_keys=reuse_keys),
        cache_keys=cache_keys,
        reuse_keys=reuse_keys,
    )


def read_compact_analysis_cache_candidate(
    *, plan: CompactAnalysisCachePlan, expected_count: int, min_model_count: int
) -> CompactAnalysisCacheCandidate | None:
    """Read one compatible generation and locate dependency-safe matching positions."""

    cached: tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], object] | None = (
        read_compact_analysis_batch(context=plan.context, batch_key=plan.batch_key)
    )
    if cached is None:
        return None
    stored_cache_keys, stored_reuse_keys, cleaned_sql, response = cached
    matching_indexes: tuple[int, ...] = tuple(
        index
        for index, (stored_key, current_key) in enumerate(
            zip(stored_reuse_keys, plan.reuse_keys, strict=False)
        )
        if stored_key == current_key
    )
    if len(stored_cache_keys) != expected_count or len(matching_indexes) < min_model_count:
        return None
    return CompactAnalysisCacheCandidate(
        matching_indexes=matching_indexes,
        preparation=CompactBatchPreparation(
            cleaned_sql=cleaned_sql,
            queries=(),
            templates=(),
            projections=(),
        ),
        response=response,
    )


def compact_analysis_batch_response_writer(
    *, plan: CompactAnalysisCachePlan, count: int
) -> CompactBatchResponseCallback:
    """Build a callback that publishes one complete compact generation."""

    def write(*, preparation: CompactBatchPreparation, response: object) -> None:
        if len(preparation.cleaned_sql) != count:
            return
        with record_compile_timing("cache_publication_ms"):
            write_compact_analysis_batch(
                context=plan.context,
                batch_key=plan.batch_key,
                cache_keys=plan.cache_keys,
                reuse_keys=plan.reuse_keys,
                cleaned_sql=preparation.cleaned_sql,
                response=response,
            )

    return write


def record_analysis_cache_metrics(
    *, batch_hits: int, entry_hits: int, misses: int, bypasses: int
) -> None:
    """Record semantic analysis cache outcomes for one invocation."""

    record_compile_metric(metric="analysis_batch_cache_hits", value=batch_hits)
    record_compile_metric(metric="analysis_entry_cache_hits", value=entry_hits)
    record_compile_metric(metric="analysis_cache_misses", value=misses)
    record_compile_metric(metric="analysis_cache_bypasses", value=bypasses)


def read_compact_analysis_batch(
    *, context: AnalysisCacheContext, batch_key: str
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], object] | None:
    """Read the newest compatible compact generation, treating every fault as a miss."""

    database_path: Path = _cache_database_path(context=context)
    if not database_path.is_file():
        return None
    try:
        connection_uri: str = f"file:{database_path}?mode=ro"
        with sqlite3.connect(
            connection_uri,
            uri=True,
            timeout=_SQLITE_TIMEOUT_SECONDS,
        ) as connection:
            metadata_row: tuple[str, int] | None = connection.execute(
                "SELECT batch_key, length(payload) FROM model_analysis_compact_batch "
                "WHERE batch_key = ?",
                (batch_key,),
            ).fetchone()
            if metadata_row is None:
                metadata_row = connection.execute(
                    "SELECT batch_key, length(payload) FROM model_analysis_compact_batch "
                    "WHERE shared_fingerprint = ? ORDER BY created_ns DESC LIMIT 1",
                    (context.shared_fingerprint,),
                ).fetchone()
            if metadata_row is None:
                return None
            stored_batch_key, payload_bytes = metadata_row
            if payload_bytes < 0 or payload_bytes > _MAX_COMPACT_BATCH_BYTES:
                return None
            payload_row: tuple[bytes] | None = connection.execute(
                "SELECT payload FROM model_analysis_compact_batch WHERE batch_key = ?",
                (stored_batch_key,),
            ).fetchone()
            if payload_row is None:
                return None
            contents: bytes = payload_row[0]
        if not isinstance(contents, bytes) or len(contents) != payload_bytes:
            return None
        envelope: object = orjson.loads(contents)
        if not isinstance(envelope, dict):
            return None
        values: dict[str, Any] = cast(dict[str, Any], envelope)
        cache_keys_value: object = values.get("cache_keys")
        reuse_keys_value: object = values.get("reuse_keys")
        cleaned_sql_value: object = values.get("cleaned_sql")
        response: object = values.get("response")
        if (
            not isinstance(cache_keys_value, list)
            or not all(isinstance(value, str) for value in cache_keys_value)
            or not isinstance(reuse_keys_value, list)
            or not all(isinstance(value, str) for value in reuse_keys_value)
            or not isinstance(cleaned_sql_value, list)
            or not all(isinstance(value, str) for value in cleaned_sql_value)
        ):
            return None
        cache_keys: tuple[str, ...] = tuple(cache_keys_value)
        reuse_keys: tuple[str, ...] = tuple(reuse_keys_value)
        cleaned_sql: tuple[str, ...] = tuple(cleaned_sql_value)
        if (
            values.get("version") != _COMPACT_BATCH_CACHE_VERSION
            or values.get("batch_key") != stored_batch_key
            or values.get("shared_fingerprint") != context.shared_fingerprint
            or values.get("count") != len(cache_keys)
            or len(reuse_keys) != len(cache_keys)
            or len(cleaned_sql) != len(cache_keys)
            or not isinstance(values.get("facts_sha256"), str)
            or not hmac.compare_digest(
                values["facts_sha256"],
                _compact_batch_facts_digest(
                    cache_keys=cache_keys,
                    reuse_keys=reuse_keys,
                    cleaned_sql=cleaned_sql,
                    response=response,
                ),
            )
        ):
            return None
        return cache_keys, reuse_keys, cleaned_sql, response
    except (OSError, sqlite3.DatabaseError, TypeError, ValueError, orjson.JSONDecodeError):
        return None


def write_compact_analysis_batch(
    *,
    context: AnalysisCacheContext,
    batch_key: str,
    cache_keys: tuple[str, ...],
    reuse_keys: tuple[str, ...],
    cleaned_sql: tuple[str, ...],
    response: object,
) -> None:
    """Persist one compact native response transactionally, with bounded logical retention."""

    try:
        if not (len(cache_keys) == len(reuse_keys) == len(cleaned_sql)):
            return
        contents: bytes = orjson.dumps(
            {
                "version": _COMPACT_BATCH_CACHE_VERSION,
                "batch_key": batch_key,
                "shared_fingerprint": context.shared_fingerprint,
                "count": len(cleaned_sql),
                "facts_sha256": _compact_batch_facts_digest(
                    cache_keys=cache_keys,
                    reuse_keys=reuse_keys,
                    cleaned_sql=cleaned_sql,
                    response=response,
                ),
                "cache_keys": cache_keys,
                "reuse_keys": reuse_keys,
                "cleaned_sql": cleaned_sql,
                "response": response,
            },
            option=orjson.OPT_SORT_KEYS,
        )
        if len(contents) > _MAX_COMPACT_BATCH_BYTES:
            return
        database_path: Path = _cache_database_path(context=context)
        database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(database_path, timeout=_SQLITE_TIMEOUT_SECONDS) as connection:
            _ = connection.execute(_CREATE_COMPACT_BATCH_TABLE_SQL)
            _ = connection.execute(
                "INSERT OR REPLACE INTO model_analysis_compact_batch "
                "(batch_key, shared_fingerprint, payload, created_ns) VALUES (?, ?, ?, ?)",
                (batch_key, context.shared_fingerprint, contents, time.time_ns()),
            )
            _ = connection.execute(
                "DELETE FROM model_analysis_compact_batch WHERE batch_key NOT IN "
                "(SELECT batch_key FROM model_analysis_compact_batch "
                "ORDER BY created_ns DESC LIMIT ?)",
                (_MAX_COMPACT_BATCH_RECORDS,),
            )
    except (OSError, sqlite3.DatabaseError, TypeError, ValueError):
        return


def _compact_batch_facts_digest(
    *,
    cache_keys: tuple[str, ...],
    reuse_keys: tuple[str, ...],
    cleaned_sql: tuple[str, ...],
    response: object,
) -> str:
    digest: Any = hashlib.sha256()
    for label, value in (
        (b"cache_keys\0", cache_keys),
        (b"reuse_keys\0", reuse_keys),
        (b"cleaned_sql\0", cleaned_sql),
        (b"response\0", response),
    ):
        digest.update(label)
        digest.update(orjson.dumps(value, option=orjson.OPT_SORT_KEYS))
        digest.update(b"\0")
    return digest.hexdigest()


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
    sources: _LineageSourceInterner = _LineageSourceInterner()
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
                            sources=sources,
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
    """Transactionally persist deterministic analyses; cache failures never fail compilation."""

    rows: list[tuple[str, str]] = []
    for cache_key, analysis in analyses_by_key.items():
        contents: str = _analysis_contents(cache_key=cache_key, analysis=analysis)
        if len(contents.encode()) <= _MAX_CACHE_ENTRY_BYTES:
            rows.append((cache_key, contents))
    signature_rows: list[tuple[str, str, str, str]] = [
        (
            context.shared_fingerprint,
            context.signature_namespace,
            model_name,
            model_analysis_output_signature(analysis),
        )
        for model_name, analysis in (latest_analyses_by_model or {}).items()
    ]
    dependency_rows: list[tuple[str, str, str, str]] = []
    for cache_key, dependencies in (dependency_signatures_by_key or {}).items():
        analysis: PolyglotAnalysisResult | None = analyses_by_key.get(cache_key)
        if analysis is None:
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

    return _json_value_digest(
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
    *,
    contents: object,
    expected_cache_key: str,
    sources: _LineageSourceInterner | None = None,
) -> tuple[PolyglotAnalysisResult, str] | None:
    if not isinstance(contents, str):
        return None
    try:
        if len(contents.encode()) > _MAX_CACHE_ENTRY_BYTES:
            return None
        stored_digest, separator, serialized_payload = contents.partition(_CACHE_ENTRY_SEPARATOR)
        if not separator or not hmac.compare_digest(
            stored_digest,
            _cache_entry_digest(
                cache_key=expected_cache_key,
                serialized_payload=serialized_payload,
            ),
        ):
            return None
        payload: object = orjson.loads(serialized_payload)
        return _analysis_from_payload(
            payload=payload, expected_cache_key=expected_cache_key, sources=sources
        )
    except (ValueError, TypeError, KeyError, RecursionError, orjson.JSONDecodeError):
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
        "function_return_types": dict(sorted(profile.function_return_types.items())),
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
        "a": analysis.analysis_succeeded,
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
        "b": [
            [
                diagnostic.code,
                diagnostic.message,
                diagnostic.line,
                diagnostic.column,
                diagnostic.start,
                diagnostic.end,
                diagnostic.severity,
            ]
            for diagnostic in analysis.binding_diagnostics
        ],
        "bv": analysis.binding_validated,
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
    *,
    payload: object,
    expected_cache_key: str,
    sources: _LineageSourceInterner | None = None,
) -> tuple[PolyglotAnalysisResult, str]:
    if not isinstance(payload, dict):
        raise AnalysisCacheEntryError("analysis cache entry must be an object")
    values: dict[str, Any] = cast(dict[str, Any], payload)
    version_value: object = values["v"]
    if type(version_value) is not int or version_value != _ANALYSIS_CACHE_VERSION:
        raise AnalysisCacheEntryError("analysis cache version mismatch")
    if values["k"] != expected_cache_key:
        raise AnalysisCacheEntryError("analysis cache key mismatch")
    analysis_succeeded: object = values["a"]
    if not isinstance(analysis_succeeded, bool):
        raise AnalysisCacheEntryError("analysis cache success flag must be a boolean")
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
    lineage_payload: list[list[object]] = _value_lists(values["l"])
    lineage_columns: Sequence[CompiledLineageColumnFact] | None = _compact_lineage_from_payload(
        payload=lineage_payload
    )
    if lineage_columns is None:
        interner: _LineageSourceInterner = _LineageSourceInterner() if sources is None else sources
        lineage_columns = tuple(
            _lineage_column_from_payload(payload=column, sources=interner)
            for column in lineage_payload
        )
    has_star: object = values["h"]
    if not isinstance(has_star, bool):
        raise AnalysisCacheEntryError("analysis cache has_star must be a boolean")
    binding_diagnostics: tuple[SqlBindingDiagnostic, ...] = tuple(
        _binding_diagnostic_from_payload(value) for value in _value_lists(values["b"])
    )
    binding_validated: object = values["bv"]
    if not isinstance(binding_validated, bool):
        raise AnalysisCacheEntryError("analysis cache binding validation flag must be a boolean")
    return (
        PolyglotAnalysisResult(
            analysis_succeeded=analysis_succeeded,
            columns=columns,
            lineage_columns=lineage_columns,
            has_star=has_star,
            binding_diagnostics=binding_diagnostics,
            binding_validated=binding_validated,
        ),
        output_signature,
    )


def _binding_diagnostic_from_payload(payload: list[object]) -> SqlBindingDiagnostic:
    diagnostic_value_count: int = 7
    if len(payload) != diagnostic_value_count:
        raise AnalysisCacheEntryError("analysis cache binding diagnostic must contain seven values")
    code, message, line, column, start, end, severity = payload
    if severity not in BINDING_SEVERITIES:
        raise AnalysisCacheEntryError("analysis cache binding diagnostic severity is invalid")
    if not isinstance(code, str) or not isinstance(message, str):
        raise AnalysisCacheEntryError(
            "analysis cache binding diagnostic code/message must be strings"
        )
    positions: tuple[object, ...] = (line, column, start, end)
    if any(value is not None and not isinstance(value, int) for value in positions):
        raise AnalysisCacheEntryError("analysis cache binding diagnostic positions are invalid")
    return SqlBindingDiagnostic(
        code=code,
        message=message,
        line=cast(int | None, line),
        column=cast(int | None, column),
        start=cast(int | None, start),
        end=cast(int | None, end),
        severity=cast(str, severity),
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
        nullability=_NULLABILITY_BY_VALUE.get(nullability) or InferredNullability(nullability),
    )


def _compact_lineage_from_payload(*, payload: list[list[object]]) -> CompactLineageFacts | None:
    """Validate cached lineage into lazy indexed rows; None means use the eager decoder."""

    pool: dict[str, int] = {}
    rows: list[tuple[int, int, int, tuple[tuple[int, int, int], ...]]] = []
    column: list[object]
    for column in payload:
        if len(column) != _LINEAGE_COLUMN_VALUE_COUNT:
            raise AnalysisCacheEntryError("analysis cache lineage column must contain four values")
        output_column, transform_kind, confidence, upstream_columns = column
        if not (
            type(output_column) is str and type(transform_kind) is str and type(confidence) is str
        ):
            raise AnalysisCacheEntryError("analysis cache lineage attributes must be strings")
        transform_code: int | None = _COMPACT_TRANSFORM_CODES.get(transform_kind)
        confidence_code: int | None = _COMPACT_CONFIDENCE_CODES.get(confidence)
        if transform_code is None or confidence_code is None:
            return None
        if type(upstream_columns) is not list:
            raise AnalysisCacheEntryError("analysis cache collection must contain arrays")
        source_rows: list[tuple[int, int, int]] = []
        source: object
        for source in upstream_columns:
            if not (
                type(source) is list
                and len(source) == _LINEAGE_SOURCE_VALUE_COUNT
                and type(source[0]) is str
                and type(source[1]) is str
                and type(source[2]) is str
            ):
                raise AnalysisCacheEntryError(
                    "analysis cache lineage source must contain three strings"
                )
            if source[0] not in _RESOURCE_TYPE_VALUES:
                raise AnalysisCacheEntryError("analysis cache lineage resource type is invalid")
            source_rows.append(
                (
                    pool.setdefault(source[0], len(pool)),
                    pool.setdefault(source[1], len(pool)),
                    pool.setdefault(source[2], len(pool)),
                )
            )
        rows.append(
            (
                pool.setdefault(output_column, len(pool)),
                transform_code,
                confidence_code,
                tuple(source_rows),
            )
        )
    return CompactLineageFacts(string_pool=tuple(pool), rows=tuple(rows))


class _LineageSourceInterner:
    """Share identical immutable lineage source facts across one cache read."""

    def __init__(self) -> None:
        self._facts: dict[tuple[str, str, str], CompiledLineageSourceFact] = {}

    def decode(self, *, payload: list[object]) -> CompiledLineageSourceFact:
        source_value_count: int = 3
        if len(payload) != source_value_count or not all(
            isinstance(value, str) for value in payload
        ):
            raise AnalysisCacheEntryError(
                "analysis cache lineage source must contain three strings"
            )
        resource_type, resource_name, column_name = cast(list[str], payload)
        key: tuple[str, str, str] = (resource_type, resource_name, column_name)
        fact: CompiledLineageSourceFact | None = self._facts.get(key)
        if fact is None:
            fact = CompiledLineageSourceFact(
                resource_type=resource_type,
                resource_name=resource_name,
                column_name=column_name,
            )
            self._facts[key] = fact
        return fact


def _lineage_column_from_payload(
    *, payload: list[object], sources: _LineageSourceInterner
) -> CompiledLineageColumnFact:
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
            sources.decode(payload=source) for source in _value_lists(upstream_columns)
        ),
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


def _json_value_digest(payload: dict[str, object]) -> str:
    """Digest string-keyed JSON scalars exactly as _payload_digest does, via orjson."""

    return hashlib.sha256(orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)).hexdigest()


def _package_version(package: str) -> str:
    try:
        return version(package)
    except PackageNotFoundError:
        return "unknown"
