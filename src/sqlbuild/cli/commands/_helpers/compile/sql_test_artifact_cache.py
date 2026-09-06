"""Persistent identities for unchanged compiled SQL test artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import platform
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import cast

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.cli.commands.models import (
    SqlTestArtifactCacheRecord,
    SqlTestArtifactIdentityContext,
)
from sqlbuild.compiler.compile.models import (
    CompiledDirectLogicSqlTestPayload,
    CompiledModel,
    CompiledModelSqlTestPayload,
    CompiledProject,
    CompiledSqlTest,
    CompileSqlTestCte,
)

_CACHE_VERSION: int = 1
_ALGORITHM_FINGERPRINT: str = "sql-test-artifact-v1"
_CACHE_FILE_NAME: str = "sql-test-artifacts.json"
_MAX_CACHE_BYTES: int = 10_000_000
_MAX_CACHE_RECORDS: int = 100_000
_PARENT_PATH_COMPONENT: str = ".."
_SQL_FILE_SUFFIX: str = ".sql"


def build_sql_test_artifact_identity_context(
    *, project: CompiledProject, adapter: BaseAdapter
) -> SqlTestArtifactIdentityContext:
    """Hash adapter and model inputs once for all test artifact identities."""

    common_identity: str = _payload_digest(
        {
            "algorithm": _ALGORITHM_FINGERPRINT,
            "sqlbuild_version": _package_version("sqlbuild"),
            "polyglot_version": _package_version("polyglot-sql"),
            "python_version": platform.python_version_tuple()[:2],
            "adapter_class": f"{type(adapter).__module__}.{type(adapter).__qualname__}",
            "set_difference_operator": adapter.render_set_difference_operator(),
            "sql_analysis_dialect": adapter.sql_analysis_dialect(),
            "requires_derived_table_aliases": adapter.requires_derived_table_aliases(),
            "sql_analysis_enabled": project.settings.sql_analysis,
            "effective_target_name": project.effective_target_name,
            "effective_target_database": project.effective_target_database,
            "effective_target_schema": project.effective_target_schema,
            "function_locations": sorted(
                (function.name, function.destination.qualified_name)
                for function in project.functions
            ),
        }
    )
    return SqlTestArtifactIdentityContext(
        common_identity=common_identity,
        model_identities={model.name: _model_identity(model=model) for model in project.models},
    )


def sql_test_artifact_identity(
    *,
    test: CompiledSqlTest,
    model_chain_names: tuple[str, ...],
    context: SqlTestArtifactIdentityContext,
) -> str:
    """Return the complete identity of one rendered comparison artifact."""

    return _payload_digest(
        {
            "common_identity": context.common_identity,
            "test": _test_payload(test=test),
            "model_chain": [
                (name, context.model_identities.get(name)) for name in model_chain_names
            ],
        }
    )


def sql_test_artifact_record_key(*, test: CompiledSqlTest) -> str:
    """Return the stable cache slot for one source test case."""

    return _payload_digest(
        {
            "source_path": None if test.source_path is None else test.source_path.as_posix(),
            "block_index": test.block_index,
            "name": test.name,
            "parent_name": test.parent_name,
            "case_name": test.case_name,
            "case_index": test.case_index,
        }
    )


def read_sql_test_artifact_cache(
    *, cache_dir: Path | None
) -> dict[str, SqlTestArtifactCacheRecord]:
    """Read valid cache records; cache failures never fail compilation."""

    if cache_dir is None:
        return {}
    cache_path: Path = cache_dir / _CACHE_FILE_NAME
    try:
        if not cache_path.is_file() or cache_path.stat().st_size > _MAX_CACHE_BYTES:
            return {}
        payload: object = json.loads(cache_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("version") != _CACHE_VERSION:
            return {}
        raw_records: object = payload.get("records")
        if not isinstance(raw_records, dict) or len(raw_records) > _MAX_CACHE_RECORDS:
            return {}
        records: dict[str, SqlTestArtifactCacheRecord] = {}
        for key, value in raw_records.items():
            record: SqlTestArtifactCacheRecord | None = _record_from_payload(value)
            if isinstance(key, str) and record is not None:
                records[key] = record
        return records
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {}


def write_sql_test_artifact_cache(
    *, cache_dir: Path | None, records: dict[str, SqlTestArtifactCacheRecord]
) -> None:
    """Atomically replace the cache snapshot; cache failures are non-fatal."""

    if cache_dir is None:
        return
    payload: dict[str, object] = {
        "version": _CACHE_VERSION,
        "records": {
            key: {
                "identity": record.identity,
                "relative_path": record.relative_path.as_posix(),
                "size": record.size,
                "mtime_ns": record.mtime_ns,
            }
            for key, record in records.items()
        },
    }
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path: Path = cache_dir / _CACHE_FILE_NAME
        temporary_path: Path = cache_dir / f".{_CACHE_FILE_NAME}.{os.getpid()}.tmp"
        temporary_path.write_text(
            json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True),
            encoding="utf-8",
        )
        temporary_path.replace(cache_path)
    except OSError:
        return


def artifact_matches_cache_record(
    *, tests_root: Path, record: SqlTestArtifactCacheRecord, identity: str
) -> Path | None:
    """Return the safe existing artifact path when identity and stat metadata match."""

    if record.identity != identity or not _is_safe_relative_sql_path(record.relative_path):
        return None
    artifact_path: Path = tests_root / record.relative_path
    try:
        stat: os.stat_result = artifact_path.stat()
    except OSError:
        return None
    if (
        not artifact_path.is_file()
        or stat.st_size != record.size
        or stat.st_mtime_ns != record.mtime_ns
    ):
        return None
    return artifact_path


def build_sql_test_artifact_cache_record(
    *, tests_root: Path, artifact_path: Path, identity: str
) -> SqlTestArtifactCacheRecord | None:
    """Capture the metadata needed to reuse one newly written artifact."""

    try:
        relative_path: Path = artifact_path.relative_to(tests_root)
        stat: os.stat_result = artifact_path.stat()
    except (OSError, ValueError):
        return None
    if not _is_safe_relative_sql_path(relative_path):
        return None
    return SqlTestArtifactCacheRecord(
        identity=identity,
        relative_path=relative_path,
        size=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
    )


def _model_identity(*, model: CompiledModel) -> str:
    return _payload_digest(
        {
            "name": model.name,
            "query_sql": model.query_sql,
            "deps": sorted((str(dep.resource_type), dep.name) for dep in model.deps),
        }
    )


def _test_payload(*, test: CompiledSqlTest) -> dict[str, object]:
    payload: dict[str, object] = {
        "case_fingerprint": test.case_fingerprint,
        "mode": test.mode.value,
        "sql_body": test.sql_body,
        "scope_deps": sorted((str(dep.resource_type), dep.name) for dep in test.scope_deps),
    }
    if isinstance(test.payload, CompiledModelSqlTestPayload):
        payload["model"] = {
            "authored_ctes": _cte_payload(test.payload.authored_ctes),
            "macro_mocks": sorted(test.payload.macro_mocks.items()),
            "model_query_overrides": sorted(test.payload.model_query_overrides.items()),
            "expected_model_names": test.payload.expected_model_names,
            "assertion_ctes": _cte_payload(test.payload.assertion_ctes),
        }
    elif isinstance(test.payload, CompiledDirectLogicSqlTestPayload):
        payload["direct"] = {
            "helper_ctes": _cte_payload(test.payload.helper_ctes),
            "actual_cte": _cte_payload((test.payload.actual_cte,)),
            "expected_cte": _cte_payload((test.payload.expected_cte,)),
            "tested_resource_names": test.payload.tested_resource_names,
        }
    return payload


def _cte_payload(ctes: tuple[CompileSqlTestCte, ...]) -> list[tuple[str, str]]:
    return [(cte.name, cte.sql_body) for cte in ctes]


def _record_from_payload(payload: object) -> SqlTestArtifactCacheRecord | None:
    if not isinstance(payload, dict):
        return None
    values: dict[str, object] = cast(dict[str, object], payload)
    identity: object = values.get("identity")
    relative_path: object = values.get("relative_path")
    size: object = values.get("size")
    mtime_ns: object = values.get("mtime_ns")
    if (
        not isinstance(identity, str)
        or not isinstance(relative_path, str)
        or not isinstance(size, int)
        or isinstance(size, bool)
        or size < 0
        or not isinstance(mtime_ns, int)
        or isinstance(mtime_ns, bool)
        or mtime_ns < 0
    ):
        return None
    path: Path = Path(relative_path)
    if not _is_safe_relative_sql_path(path):
        return None
    return SqlTestArtifactCacheRecord(
        identity=identity,
        relative_path=path,
        size=size,
        mtime_ns=mtime_ns,
    )


def _is_safe_relative_sql_path(path: Path) -> bool:
    return (
        not path.is_absolute()
        and _PARENT_PATH_COMPONENT not in path.parts
        and path.suffix == _SQL_FILE_SUFFIX
    )


def _payload_digest(payload: object) -> str:
    encoded: str = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _package_version(package_name: str) -> str:
    try:
        return version(package_name)
    except PackageNotFoundError:
        return "unknown"
