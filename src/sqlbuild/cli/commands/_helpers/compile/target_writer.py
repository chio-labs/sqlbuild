"""Write compiled project output to the target/ directory."""

from __future__ import annotations

import json
import os
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
from sqlbuild.cli.compile.models import (
    SqlTestArtifactCacheRecord,
    SqlTestArtifactIdentityContext,
)
from sqlbuild.cli.output.models import (
    WrittenTarget,
)
from sqlbuild.cli.paths.main._compiled_sql_test_output_path import (
    compiled_sql_test_output_path,
)
from sqlbuild.cli.paths.main._sql_test_output_path import sql_test_output_path
from sqlbuild.compiler.compile.models import (
    CompiledObjectKey,
    CompiledProject,
    CompiledSqlTest,
    CompilerDiagnostic,
)
from sqlbuild.compiler.compile.types import (
    CompiledResourceType,
    DiagnosticPhase,
    DiagnosticSeverity,
    FunctionLanguage,
)
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.main.execution.sql_test_artifacts import (
    plan_and_render_sql_test_artifacts,
)
from sqlbuild.compiler.planner.main.execution.sql_test_model_chain import (
    sql_test_model_chain_names_by_key,
)
from sqlbuild.compiler.planner.models import AuditPlanEntry, NativeSqlTestArtifact, PlanOutput
from sqlbuild.compiler.profiling.main.record import record_compile_timing
from sqlbuild.executor.testing.main.comparison_sql import build_sql_test_comparison_sql
from sqlbuild.runtime.observability.classes.operation_lifecycle import OperationLifecycle

_COMPILED_DIR: str = "compiled"
_MODELS_DIR: str = "models"
_FUNCTIONS_DIR: str = "functions"
_AUDITS_DIR: str = "audits"
_GENERIC_DIR: str = "generic"
_SINGULAR_DIR: str = "singular"
_TESTS_DIR: str = "tests"
_MANIFEST_FILE: str = "manifest.json"
_SQL_FILE_SUFFIX: str = ".sql"
_POSIX_LINE_SEPARATOR: str = "\n"
_SQL_TEST_PLANNING_ERROR_CODE: str = PlannerInputError.code


def write_compile_target(
    *,
    target_dir: Path,
    adapter: BaseAdapter,
    plan_output: PlanOutput,
    manifest: dict[str, object] | None = None,
) -> WrittenTarget:
    """Write compiled output files under target_dir."""

    remove_stale_files: bool = (target_dir / _COMPILED_DIR).is_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    managed_paths: set[Path] = set().union(
        _write_models(
            target_dir=target_dir,
            plan_output=plan_output,
            check_existing=remove_stale_files,
        ),
        _write_functions(
            target_dir=target_dir,
            adapter=adapter,
            plan_output=plan_output,
            check_existing=remove_stale_files,
        ),
        _write_audits(
            target_dir=target_dir,
            plan_output=plan_output,
            check_existing=remove_stale_files,
        ),
        _write_tests(
            target_dir=target_dir,
            adapter=adapter,
            plan_output=plan_output,
            check_existing=remove_stale_files,
        ),
    )
    if remove_stale_files:
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

    remove_stale_files: bool = (target_dir / _COMPILED_DIR).is_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    managed_paths: set[Path] = set().union(
        _write_static_models(
            target_dir=target_dir,
            project=project,
            check_existing=remove_stale_files,
        ),
        _write_static_functions(
            target_dir=target_dir,
            adapter=adapter,
            project=project,
            check_existing=remove_stale_files,
        ),
        _write_static_audits(
            target_dir=target_dir,
            project=project,
            check_existing=remove_stale_files,
        ),
    )
    test_paths, test_diagnostics = _write_static_tests(
        target_dir=target_dir,
        adapter=adapter,
        project=project,
        check_existing=remove_stale_files,
    )
    managed_paths.update(test_paths)
    if remove_stale_files:
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
        diagnostics=test_diagnostics,
    )


def publish_static_compile_target(
    *, prepared: WrittenTarget, target_dir: Path, manifest: dict[str, object] | None
) -> WrittenTarget:
    """Publish staged files with the same unchanged-file and stale-file semantics."""

    compiled_dir: Path = target_dir / _COMPILED_DIR
    staged_dir: Path = prepared.target_dir / _COMPILED_DIR
    check_existing: bool = compiled_dir.is_dir()
    managed_paths: set[Path] = set()
    target_dir.mkdir(parents=True, exist_ok=True)
    for source in sorted(staged_dir.rglob("*")):
        if not source.is_file():
            continue
        path: Path = compiled_dir / source.relative_to(staged_dir)
        _write_bytes_if_changed(
            path=path, contents=source.read_bytes(), check_existing=check_existing
        )
        managed_paths.add(path)
    if check_existing:
        with record_compile_timing("stale_traversal_ms"):
            _remove_stale_compiled_files(target_dir=target_dir, managed_paths=managed_paths)
    if manifest is not None:
        _write_manifest(target_dir=target_dir, manifest=manifest)
    return WrittenTarget(
        model_count=prepared.model_count,
        seed_count=prepared.seed_count,
        function_count=prepared.function_count,
        audit_count=prepared.audit_count,
        test_count=prepared.test_count,
        target_dir=target_dir,
        diagnostics=prepared.diagnostics,
    )


def _write_models(*, target_dir: Path, plan_output: PlanOutput, check_existing: bool) -> set[Path]:
    """Write model resolved SQL."""

    managed_paths: set[Path] = set()
    for entry in plan_output.model_entries:
        compiled_path: Path = target_dir / _COMPILED_DIR / _model_output_path(entry.relative_path)
        _write_sql(path=compiled_path, sql=entry.resolved_sql, check_existing=check_existing)
        managed_paths.add(compiled_path)
    return managed_paths


def _write_static_models(
    *, target_dir: Path, project: CompiledProject, check_existing: bool
) -> set[Path]:
    """Write offline model query SQL."""

    managed_paths: set[Path] = set()
    for model in project.models:
        compiled_path: Path = target_dir / _COMPILED_DIR / _model_output_path(model.relative_path)
        _write_sql(path=compiled_path, sql=model.query_sql, check_existing=check_existing)
        managed_paths.add(compiled_path)
    return managed_paths


def _write_functions(
    *,
    target_dir: Path,
    adapter: BaseAdapter,
    plan_output: PlanOutput,
    check_existing: bool,
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
            check_existing=check_existing,
        )
        managed_paths.add(function_path)
    return managed_paths


def _write_static_functions(
    *,
    target_dir: Path,
    adapter: BaseAdapter,
    project: CompiledProject,
    check_existing: bool,
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
            check_existing=check_existing,
        )
        managed_paths.add(function_path)
    return managed_paths


def _write_audits(*, target_dir: Path, plan_output: PlanOutput, check_existing: bool) -> set[Path]:
    """Write resolved audit SQL."""

    managed_paths: set[Path] = set()
    for entry in plan_output.audit_entries:
        folder: Path = _audit_folder(entry)
        file_name: str = _audit_file_name(entry)
        audit_path: Path = target_dir / _COMPILED_DIR / _AUDITS_DIR / folder / file_name
        _write_sql(path=audit_path, sql=entry.resolved_sql, check_existing=check_existing)
        managed_paths.add(audit_path)
    return managed_paths


def _write_static_audits(
    *, target_dir: Path, project: CompiledProject, check_existing: bool
) -> set[Path]:
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
        _write_sql(path=audit_path, sql=audit.sql_body, check_existing=check_existing)
        managed_paths.add(audit_path)
    return managed_paths


def _write_tests(
    *,
    target_dir: Path,
    adapter: BaseAdapter,
    plan_output: PlanOutput,
    check_existing: bool,
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
        _write_sql(path=test_path, sql=comparison_sql, check_existing=check_existing)
        managed_paths.add(test_path)
    return managed_paths


def static_sql_test_planning_diagnostics(
    *, target_dir: Path, adapter: BaseAdapter, project: CompiledProject
) -> tuple[CompilerDiagnostic, ...]:
    """Plan uncached SQL tests and report their errors without writing artifacts or cache."""

    pending, _, _ = _partition_cached_static_tests(
        tests_root=target_dir / _COMPILED_DIR / _TESTS_DIR, adapter=adapter, project=project
    )
    tests: tuple[CompiledSqlTest, ...] = tuple(test for test, _, _ in pending)
    artifacts: tuple[NativeSqlTestArtifact, ...] = _plan_static_test_artifacts(
        adapter=adapter, project=project, tests=tests
    )
    diagnostics: list[CompilerDiagnostic] = []
    for test, artifact in zip(tests, artifacts, strict=True):
        diagnostics.extend(_sql_test_artifact_diagnostics(test=test, artifact=artifact))
    return tuple(diagnostics)


def _partition_cached_static_tests(
    *, tests_root: Path, adapter: BaseAdapter, project: CompiledProject
) -> tuple[
    list[tuple[CompiledSqlTest, str | None, str | None]],
    set[Path],
    dict[str, SqlTestArtifactCacheRecord],
]:
    """Split SQL tests into pending work and reusable cached artifacts."""

    managed_paths: set[Path] = set()
    cached_records: dict[str, SqlTestArtifactCacheRecord] = read_sql_test_artifact_cache(
        cache_dir=project.compile_cache_dir
    )
    current_records: dict[str, SqlTestArtifactCacheRecord] = {}
    identity_context: SqlTestArtifactIdentityContext | None = (
        build_sql_test_artifact_identity_context(project=project, adapter=adapter)
        if project.compile_cache_dir is not None
        else None
    )
    model_chain_names_by_key: dict[CompiledObjectKey, tuple[str, ...]] = {}
    if identity_context is not None:
        model_chain_names_by_key = sql_test_model_chain_names_by_key(
            project=project,
            tests=project.sql_tests,
        )
    pending: list[tuple[CompiledSqlTest, str | None, str | None]] = []
    for test in project.sql_tests:
        record_key: str | None = None
        artifact_identity: str | None = None
        if identity_context is not None:
            record_key = sql_test_artifact_record_key(test=test)
            artifact_identity = sql_test_artifact_identity(
                test=test,
                model_chain_names=model_chain_names_by_key.get(test.key, ()),
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
        pending.append((test, record_key, artifact_identity))
    return pending, managed_paths, current_records


def _plan_static_test_artifacts(
    *, adapter: BaseAdapter, project: CompiledProject, tests: tuple[CompiledSqlTest, ...]
) -> tuple[NativeSqlTestArtifact, ...]:
    if not tests:
        return ()
    with OperationLifecycle(
        operation_kind="project", operation_name="sql_test_planning"
    ) as lifecycle:
        native_artifacts: tuple[NativeSqlTestArtifact, ...] = plan_and_render_sql_test_artifacts(
            project=project,
            tests=tests,
            adapter=adapter,
            sql_analysis_enabled=project.settings.sql_analysis,
        )
        lifecycle.completed(metadata={"item_count": len(native_artifacts)})
    return native_artifacts


def _write_static_tests(
    *,
    target_dir: Path,
    adapter: BaseAdapter,
    project: CompiledProject,
    check_existing: bool,
) -> tuple[set[Path], tuple[CompilerDiagnostic, ...]]:
    """Write offline SQL-native test SQL and report uncached planning errors."""

    diagnostics: list[CompilerDiagnostic] = []
    tests_root: Path = target_dir / _COMPILED_DIR / _TESTS_DIR
    pending, managed_paths, current_records = _partition_cached_static_tests(
        tests_root=tests_root, adapter=adapter, project=project
    )
    native_artifacts: tuple[NativeSqlTestArtifact, ...] = _plan_static_test_artifacts(
        adapter=adapter, project=project, tests=tuple(test for test, _, _ in pending)
    )
    for (test, record_key, artifact_identity), artifact in zip(
        pending, native_artifacts, strict=True
    ):
        test_path: Path = tests_root / compiled_sql_test_output_path(
            test=test,
            model_names=artifact.model_names,
        )
        _write_sql(path=test_path, sql=artifact.sql, check_existing=check_existing)
        managed_paths.add(test_path)
        artifact_diagnostics: tuple[CompilerDiagnostic, ...] = _sql_test_artifact_diagnostics(
            test=test, artifact=artifact
        )
        if artifact_diagnostics:
            diagnostics.extend(artifact_diagnostics)
            continue
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
    return managed_paths, tuple(diagnostics)


def _sql_test_artifact_diagnostics(
    *, test: CompiledSqlTest, artifact: NativeSqlTestArtifact
) -> tuple[CompilerDiagnostic, ...]:
    return tuple(
        CompilerDiagnostic(
            phase=DiagnosticPhase.TEST,
            severity=DiagnosticSeverity.ERROR,
            code=_SQL_TEST_PLANNING_ERROR_CODE,
            message=message,
            resource_type=CompiledResourceType.SQL_TEST,
            resource_name=test.name,
            path=test.source_path,
        )
        for message in artifact.error_messages
    )


def _write_manifest(*, target_dir: Path, manifest: dict[str, object]) -> None:
    """Write manifest.json."""

    manifest_path: Path = target_dir / _MANIFEST_FILE
    _write_text_if_changed(path=manifest_path, contents=json.dumps(manifest, indent=2) + "\n")


def _write_sql(*, path: Path, sql: str, check_existing: bool = True) -> None:
    """Write one SQL file."""

    contents: str = sql.rstrip() + "\n"
    if os.linesep != _POSIX_LINE_SEPARATOR:
        _write_text_if_changed(
            path=path,
            contents=contents,
            check_existing=check_existing,
        )
        return
    _write_bytes_if_changed(
        path=path,
        contents=contents.encode("utf-8"),
        check_existing=check_existing,
    )


def _write_text_if_changed(*, path: Path, contents: str, check_existing: bool = True) -> None:
    with record_compile_timing("physical_write_ms"):
        if check_existing and path.is_file() and path.read_text(encoding="utf-8") == contents:
            return
        try:
            _overwrite_text(path=path, contents=contents)
        except FileNotFoundError:
            path.parent.mkdir(parents=True, exist_ok=True)
            _overwrite_text(path=path, contents=contents)


def _write_bytes_if_changed(*, path: Path, contents: bytes, check_existing: bool = True) -> None:
    with record_compile_timing("physical_write_ms"):
        if check_existing and path.is_file():
            existing: bytes = path.read_bytes()
            if existing == contents:
                return
            _ = existing.decode("utf-8")
        try:
            _overwrite_bytes(path=path, contents=contents)
        except FileNotFoundError:
            path.parent.mkdir(parents=True, exist_ok=True)
            _overwrite_bytes(path=path, contents=contents)


def _overwrite_text(*, path: Path, contents: str) -> None:
    _ = path.write_text(contents, encoding="utf-8")


def _overwrite_bytes(*, path: Path, contents: bytes) -> None:
    descriptor: int = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o666)
    try:
        offset: int = 0
        while offset < len(contents):
            written: int = os.write(descriptor, contents[offset:])
            if written == 0:
                raise OSError(f"failed to write compiled artifact '{path}'")
            offset += written
    finally:
        os.close(descriptor)


def _remove_stale_compiled_files(*, target_dir: Path, managed_paths: set[Path]) -> None:
    compiled_dir: Path = target_dir / _COMPILED_DIR
    if not compiled_dir.is_dir():
        return
    managed_names: set[str] = {os.fspath(path) for path in managed_paths}
    for root, directories, filenames in os.walk(compiled_dir, topdown=False):
        for filename in filenames:
            path: str = os.path.join(root, filename)
            if path not in managed_names:
                os.unlink(path)
        for name in directories:
            _remove_empty_directory(os.path.join(root, name))
    _remove_empty_directory(compiled_dir)


def _remove_empty_directory(directory: str | Path) -> None:
    try:
        os.rmdir(directory)
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
