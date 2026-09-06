"""Write compiled project output to the target/ directory."""

from __future__ import annotations

import json
from pathlib import Path

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.cli.commands._helpers.compile.sql_test_artifact_cache import (
    artifact_matches_cache_record,
    build_sql_test_artifact_cache_record,
    build_sql_test_artifact_identity_context,
    read_sql_test_artifact_cache,
    sql_test_artifact_identity,
    sql_test_artifact_record_key,
    write_sql_test_artifact_cache,
)
from sqlbuild.cli.commands.models import (
    SqlTestArtifactCacheRecord,
    SqlTestArtifactIdentityContext,
    WrittenTarget,
)
from sqlbuild.cli.paths.main._sql_test_output_path import sql_test_output_path
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.compile.types import FunctionLanguage
from sqlbuild.compiler.planner.main.execution.sql_test_assembly import (
    _sql_test_model_chain_names,
    build_sql_test_plan_entry,
)
from sqlbuild.compiler.planner.models import AuditPlanEntry, PlanOutput
from sqlbuild.compiler.profiling.main.record import record_compile_timing
from sqlbuild.executor.testing.main.comparison_sql import build_sql_test_comparison_sql

_COMPILED_DIR: str = "compiled"
_RUN_DIR: str = "run"
_MODELS_DIR: str = "models"
_FUNCTIONS_DIR: str = "functions"
_SQL_FUNCTIONS_DIR: str = "sql"
_AUDITS_DIR: str = "audits"
_GENERIC_DIR: str = "generic"
_SINGULAR_DIR: str = "singular"
_TESTS_DIR: str = "tests"
_MANIFEST_FILE: str = "manifest.json"
_SQL_FILE_SUFFIX: str = ".sql"


def write_compile_target(
    *,
    target_dir: Path,
    adapter: BaseAdapter,
    plan_output: PlanOutput,
    manifest: dict[str, object] | None = None,
) -> WrittenTarget:
    """Write compiled output files under target_dir."""

    target_dir.mkdir(parents=True, exist_ok=True)
    managed_paths: set[Path] = set().union(
        _write_models(target_dir=target_dir, plan_output=plan_output),
        _write_functions(target_dir=target_dir, adapter=adapter, plan_output=plan_output),
        _write_audits(target_dir=target_dir, plan_output=plan_output),
        _write_tests(target_dir=target_dir, adapter=adapter, plan_output=plan_output),
    )
    with record_compile_timing("stale_traversal_ms"):
        _remove_stale_compiled_files(target_dir=target_dir, managed_paths=managed_paths)
    if manifest is not None:
        _write_manifest(target_dir=target_dir, manifest=manifest)

    return WrittenTarget(
        model_count=len(plan_output.model_entries),
        seed_count=len(plan_output.seed_entries),
        function_count=len(plan_output.function_entries),
        audit_count=len(plan_output.audit_entries),
        test_count=len(plan_output.test_entries),
        target_dir=target_dir,
    )


def write_static_compile_target(
    *,
    target_dir: Path,
    adapter: BaseAdapter,
    project: CompiledProject,
    manifest: dict[str, object] | None = None,
) -> WrittenTarget:
    """Write offline compiled output files under target_dir."""

    target_dir.mkdir(parents=True, exist_ok=True)
    managed_paths: set[Path] = set().union(
        _write_static_models(target_dir=target_dir, project=project),
        _write_static_functions(target_dir=target_dir, adapter=adapter, project=project),
        _write_static_audits(target_dir=target_dir, project=project),
        _write_static_tests(target_dir=target_dir, adapter=adapter, project=project),
    )
    with record_compile_timing("stale_traversal_ms"):
        _remove_stale_compiled_files(target_dir=target_dir, managed_paths=managed_paths)
    if manifest is not None:
        _write_manifest(target_dir=target_dir, manifest=manifest)

    return WrittenTarget(
        model_count=len(project.models),
        seed_count=len(project.seeds),
        function_count=len(project.functions),
        audit_count=len(project.audits),
        test_count=len(project.sql_tests),
        target_dir=target_dir,
    )


def _write_models(*, target_dir: Path, plan_output: PlanOutput) -> set[Path]:
    """Write model resolved SQL."""

    managed_paths: set[Path] = set()
    for entry in plan_output.model_entries:
        compiled_path: Path = target_dir / _COMPILED_DIR / _model_output_path(entry.relative_path)
        _write_sql(path=compiled_path, sql=entry.resolved_sql)
        managed_paths.add(compiled_path)
    return managed_paths


def _write_static_models(*, target_dir: Path, project: CompiledProject) -> set[Path]:
    """Write offline model query SQL."""

    managed_paths: set[Path] = set()
    for model in project.models:
        compiled_path: Path = target_dir / _COMPILED_DIR / _model_output_path(model.relative_path)
        _write_sql(path=compiled_path, sql=model.query_sql)
        managed_paths.add(compiled_path)
    return managed_paths


def _write_functions(
    *,
    target_dir: Path,
    adapter: BaseAdapter,
    plan_output: PlanOutput,
) -> set[Path]:
    """Write executable SQL function DDL."""

    managed_paths: set[Path] = set()
    for entry in plan_output.function_entries:
        if entry.destination.qualified_name is None:
            continue
        statements: tuple[str, ...] = adapter.render_create_function(
            destination=entry.destination.qualified_name,
            arguments=entry.arguments,
            returns=entry.returns,
            body_sql=entry.body_sql,
            return_columns=entry.return_columns,
            language=entry.language,
            runtime_version=entry.runtime_version,
            entry_point=entry.entry_point,
            packages=entry.packages,
        )
        function_path: Path = (
            target_dir
            / _COMPILED_DIR
            / _function_output_path(relative_path=entry.relative_path, language=entry.language)
        )
        _write_sql(
            path=function_path,
            sql=";\n\n".join(statements),
        )
        managed_paths.add(function_path)
    return managed_paths


def _write_static_functions(
    *,
    target_dir: Path,
    adapter: BaseAdapter,
    project: CompiledProject,
) -> set[Path]:
    """Write offline rendered SQL function DDL."""

    managed_paths: set[Path] = set()
    for function in project.functions:
        if function.destination.qualified_name is None:
            continue
        statements: tuple[str, ...] = adapter.render_create_function(
            destination=function.destination.qualified_name,
            arguments=function.arguments,
            returns=function.returns,
            body_sql=function.body_sql,
            return_columns=function.return_columns,
            language=function.language,
            runtime_version=function.runtime_version,
            entry_point=function.entry_point,
            packages=function.packages,
        )
        function_path: Path = (
            target_dir
            / _COMPILED_DIR
            / _function_output_path(
                relative_path=function.relative_path, language=function.language
            )
        )
        _write_sql(
            path=function_path,
            sql=";\n\n".join(statements),
        )
        managed_paths.add(function_path)
    return managed_paths


def _write_audits(*, target_dir: Path, plan_output: PlanOutput) -> set[Path]:
    """Write resolved audit SQL."""

    managed_paths: set[Path] = set()
    for entry in plan_output.audit_entries:
        folder: Path = _audit_folder(entry)
        file_name: str = _audit_file_name(entry)
        audit_path: Path = target_dir / _COMPILED_DIR / _AUDITS_DIR / folder / file_name
        _write_sql(path=audit_path, sql=entry.resolved_sql)
        managed_paths.add(audit_path)
    return managed_paths


def _write_static_audits(*, target_dir: Path, project: CompiledProject) -> set[Path]:
    """Write offline resolved audit SQL."""

    managed_paths: set[Path] = set()
    for audit in project.audits:
        folder: Path = _static_audit_folder(attached_target_name=audit.attached_target_name)
        file_name: str = _static_audit_file_name(
            name=audit.name,
            attached_target_name=audit.attached_target_name,
            attached_column_name=audit.attached_column_name,
        )
        audit_path: Path = target_dir / _COMPILED_DIR / _AUDITS_DIR / folder / file_name
        _write_sql(path=audit_path, sql=audit.sql_body)
        managed_paths.add(audit_path)
    return managed_paths


def _write_tests(
    *,
    target_dir: Path,
    adapter: BaseAdapter,
    plan_output: PlanOutput,
) -> set[Path]:
    """Write resolved SQL-native test SQL."""

    managed_paths: set[Path] = set()
    for entry in plan_output.test_entries:
        test_path: Path = target_dir / _COMPILED_DIR / _TESTS_DIR / sql_test_output_path(entry)
        with record_compile_timing("comparison_render_ms"):
            comparison_sql: str = build_sql_test_comparison_sql(
                test_entry=entry,
                set_difference_operator=adapter.render_set_difference_operator(),
                sql_analysis_dialect=adapter.sql_analysis_dialect(),
            )
        _write_sql(path=test_path, sql=comparison_sql)
        managed_paths.add(test_path)
    return managed_paths


def _write_static_tests(
    *,
    target_dir: Path,
    adapter: BaseAdapter,
    project: CompiledProject,
) -> set[Path]:
    """Write offline SQL-native test SQL."""

    managed_paths: set[Path] = set()
    tests_root: Path = target_dir / _COMPILED_DIR / _TESTS_DIR
    cached_records: dict[str, SqlTestArtifactCacheRecord] = read_sql_test_artifact_cache(
        cache_dir=project.compile_cache_dir
    )
    current_records: dict[str, SqlTestArtifactCacheRecord] = {}
    identity_context: SqlTestArtifactIdentityContext | None = (
        build_sql_test_artifact_identity_context(project=project, adapter=adapter)
        if project.compile_cache_dir is not None
        else None
    )
    for test in project.sql_tests:
        record_key: str | None = None
        artifact_identity: str | None = None
        if identity_context is not None:
            record_key = sql_test_artifact_record_key(test=test)
            artifact_identity = sql_test_artifact_identity(
                test=test,
                model_chain_names=_sql_test_model_chain_names(test=test, project=project),
                context=identity_context,
            )
            cached_record: SqlTestArtifactCacheRecord | None = cached_records.get(record_key)
            if cached_record is not None:
                cached_path: Path | None = artifact_matches_cache_record(
                    tests_root=tests_root,
                    record=cached_record,
                    identity=artifact_identity,
                )
                if cached_path is not None:
                    managed_paths.add(cached_path)
                    current_records[record_key] = cached_record
                    continue
        with record_compile_timing("test_planning_ms"):
            entry, _warnings = build_sql_test_plan_entry(
                test=test,
                project=project,
                adapter=adapter,
                sql_analysis_enabled=project.settings.sql_analysis,
            )
        test_path: Path = tests_root / sql_test_output_path(entry)
        with record_compile_timing("comparison_render_ms"):
            comparison_sql: str = build_sql_test_comparison_sql(
                test_entry=entry,
                set_difference_operator=adapter.render_set_difference_operator(),
                sql_analysis_dialect=adapter.sql_analysis_dialect(),
            )
        _write_sql(path=test_path, sql=comparison_sql)
        managed_paths.add(test_path)
        if record_key is not None and artifact_identity is not None:
            record: SqlTestArtifactCacheRecord | None = build_sql_test_artifact_cache_record(
                tests_root=tests_root,
                artifact_path=test_path,
                identity=artifact_identity,
            )
            if record is not None:
                current_records[record_key] = record
    with record_compile_timing("cache_publication_ms"):
        write_sql_test_artifact_cache(
            cache_dir=project.compile_cache_dir,
            records=current_records,
        )
    return managed_paths


def _write_manifest(*, target_dir: Path, manifest: dict[str, object]) -> None:
    """Write manifest.json."""

    manifest_path: Path = target_dir / _MANIFEST_FILE
    _write_text_if_changed(path=manifest_path, contents=json.dumps(manifest, indent=2) + "\n")


def _write_sql(*, path: Path, sql: str) -> None:
    """Write one SQL file."""

    _write_text_if_changed(path=path, contents=sql.rstrip() + "\n")


def _write_text_if_changed(*, path: Path, contents: str) -> None:
    with record_compile_timing("physical_write_ms"):
        if path.is_file() and path.read_text(encoding="utf-8") == contents:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")


def _remove_stale_compiled_files(*, target_dir: Path, managed_paths: set[Path]) -> None:
    compiled_dir: Path = target_dir / _COMPILED_DIR
    if not compiled_dir.is_dir():
        return
    for path in compiled_dir.rglob("*"):
        if path.is_file() and path not in managed_paths:
            path.unlink()
    directories: list[Path] = sorted(
        (path for path in compiled_dir.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    )
    for directory in (*directories, compiled_dir):
        try:
            directory.rmdir()
        except OSError:
            pass


def _model_output_path(relative_path: Path) -> Path:
    parts: tuple[str, ...] = relative_path.parts
    if parts and parts[0] == _MODELS_DIR:
        return Path(*parts)
    return Path(_MODELS_DIR) / relative_path


def _function_output_path(*, relative_path: Path, language: FunctionLanguage) -> Path:
    parts: tuple[str, ...] = relative_path.parts
    language_dir: str = language.value
    function_language_path_part_count: int = 2
    if (
        len(parts) >= function_language_path_part_count
        and parts[0] == _FUNCTIONS_DIR
        and parts[1] == language_dir
    ):
        return Path(*parts).with_suffix(_SQL_FILE_SUFFIX)
    return (Path(_FUNCTIONS_DIR) / language_dir / relative_path).with_suffix(_SQL_FILE_SUFFIX)


def _audit_folder(entry: AuditPlanEntry) -> Path:
    """Determine the audit output folder."""

    if entry.attached_target_name is not None:
        return Path(_GENERIC_DIR) / entry.attached_target_name
    return Path(_SINGULAR_DIR)


def _static_audit_folder(*, attached_target_name: str | None) -> Path:
    """Determine the offline audit output folder."""

    if attached_target_name is not None:
        return Path(_GENERIC_DIR) / attached_target_name
    return Path(_SINGULAR_DIR)


def _audit_file_name(entry: AuditPlanEntry) -> str:
    """Determine the audit output file name."""

    if entry.attached_target_name is not None and entry.attached_column_name is not None:
        return f"{entry.name}__{entry.attached_column_name}{_SQL_FILE_SUFFIX}"
    return f"{entry.name}{_SQL_FILE_SUFFIX}"


def _static_audit_file_name(
    *,
    name: str,
    attached_target_name: str | None,
    attached_column_name: str | None,
) -> str:
    """Determine the offline audit output file name."""

    if attached_target_name is not None and attached_column_name is not None:
        return f"{name}__{attached_column_name}{_SQL_FILE_SUFFIX}"
    return f"{name}{_SQL_FILE_SUFFIX}"
