"""Write compiled project output to the target/ directory."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.helpers.compile.models import WrittenTarget
from sqlbuild.compiler.planner.models import AuditPlanEntry, PlanOutput, SqlTestPlanEntry
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
_CHAIN_DIR: str = "_chain_"
_MANIFEST_FILE: str = "manifest.json"
_SQL_FILE_SUFFIX: str = ".sql"


def write_compile_target(
    *,
    target_dir: Path,
    adapter: BaseAdapter,
    plan_output: PlanOutput,
    manifest: dict[str, object],
) -> WrittenTarget:
    """Write compiled output files under target_dir."""

    _clean_target(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    _write_models(target_dir=target_dir, plan_output=plan_output)
    _write_functions(target_dir=target_dir, adapter=adapter, plan_output=plan_output)
    _write_audits(target_dir=target_dir, plan_output=plan_output)
    _write_tests(target_dir=target_dir, adapter=adapter, plan_output=plan_output)
    _write_manifest(target_dir=target_dir, manifest=manifest)

    return WrittenTarget(
        model_count=len(plan_output.model_entries),
        seed_count=len(plan_output.seed_entries),
        function_count=len(plan_output.function_entries),
        audit_count=len(plan_output.audit_entries),
        test_count=len(plan_output.test_entries),
        target_dir=target_dir,
    )


def _clean_target(target_dir: Path) -> None:
    """Remove generated compile output directories from target/."""

    compiled_dir: Path = target_dir / _COMPILED_DIR
    if compiled_dir.exists():
        shutil.rmtree(compiled_dir)


def _write_models(*, target_dir: Path, plan_output: PlanOutput) -> None:
    """Write model resolved SQL."""

    for entry in plan_output.model_entries:
        compiled_path: Path = target_dir / _COMPILED_DIR / _model_output_path(entry.relative_path)
        _write_sql(path=compiled_path, sql=entry.resolved_sql)


def _write_functions(*, target_dir: Path, adapter: BaseAdapter, plan_output: PlanOutput) -> None:
    """Write executable SQL function DDL."""

    for entry in plan_output.function_entries:
        if entry.target.qualified_name is None:
            continue
        statements: tuple[str, ...] = adapter.render_create_function(
            target=entry.target.qualified_name,
            arguments=entry.arguments,
            returns=entry.returns,
            body_sql=entry.body_sql,
            language=entry.language,
            runtime_version=entry.runtime_version,
            entry_point=entry.entry_point,
            packages=entry.packages,
        )
        function_path: Path = (
            target_dir / _COMPILED_DIR / _function_output_path(entry.relative_path)
        )
        _write_sql(path=function_path, sql=";\n\n".join(statements))


def _write_audits(*, target_dir: Path, plan_output: PlanOutput) -> None:
    """Write resolved audit SQL."""

    for entry in plan_output.audit_entries:
        folder: Path = _audit_folder(entry)
        file_name: str = _audit_file_name(entry)
        audit_path: Path = target_dir / _COMPILED_DIR / _AUDITS_DIR / folder / file_name
        _write_sql(path=audit_path, sql=entry.resolved_sql)


def _write_tests(*, target_dir: Path, adapter: BaseAdapter, plan_output: PlanOutput) -> None:
    """Write resolved SQL-native test SQL."""

    for entry in plan_output.test_entries:
        test_path: Path = (
            target_dir / _COMPILED_DIR / _TESTS_DIR / _test_folder(entry) / f"{entry.name}.sql"
        )
        _write_sql(
            path=test_path,
            sql=build_sql_test_comparison_sql(
                entry,
                set_difference_operator=adapter.render_set_difference_operator(),
                sqlglot_dialect=adapter.sqlglot_dialect(),
            ),
        )


def _write_manifest(*, target_dir: Path, manifest: dict[str, object]) -> None:
    """Write manifest.json."""

    manifest_path: Path = target_dir / _MANIFEST_FILE
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def _write_sql(*, path: Path, sql: str) -> None:
    """Write one SQL file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(sql.rstrip() + "\n", encoding="utf-8")


def _model_output_path(relative_path: Path) -> Path:
    parts: tuple[str, ...] = relative_path.parts
    if parts and parts[0] == _MODELS_DIR:
        return Path(*parts)
    return Path(_MODELS_DIR) / relative_path


def _function_output_path(relative_path: Path) -> Path:
    parts: tuple[str, ...] = relative_path.parts
    if len(parts) >= 2 and parts[0] == _FUNCTIONS_DIR and parts[1] == _SQL_FUNCTIONS_DIR:
        return Path(*parts)
    return Path(_FUNCTIONS_DIR) / _SQL_FUNCTIONS_DIR / relative_path


def _audit_folder(entry: AuditPlanEntry) -> Path:
    """Determine the audit output folder."""

    if entry.attached_target_name is not None:
        return Path(_GENERIC_DIR) / entry.attached_target_name
    return Path(_SINGULAR_DIR)


def _audit_file_name(entry: AuditPlanEntry) -> str:
    """Determine the audit output file name."""

    if entry.attached_target_name is not None and entry.attached_column_name is not None:
        return f"{entry.name}__{entry.attached_column_name}{_SQL_FILE_SUFFIX}"
    return f"{entry.name}{_SQL_FILE_SUFFIX}"


def _test_folder(entry: SqlTestPlanEntry) -> Path:
    """Determine the SQL-native test output folder."""

    model_names: list[str] = [step.model_name for step in entry.chain]
    unique_names: list[str] = sorted(set(model_names))
    if len(unique_names) <= 1:
        return Path(unique_names[0] if unique_names else entry.name)
    return Path(_CHAIN_DIR) / "__".join(unique_names)
