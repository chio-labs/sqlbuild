from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.cli.commands._helpers.compile import target_writer as target_writer_module
from sqlbuild.cli.commands._helpers.compile.target_writer import (
    write_compile_target,
    write_static_compile_target,
)
from sqlbuild.cli.commands.models import WrittenTarget
from sqlbuild.compiler.compile.models import CompiledModel, CompiledProject, CompiledSqlTest
from sqlbuild.compiler.planner.models import ChainStep, PlanOutput, SqlTestPlanEntry
from sqlbuild.executor.testing.main.comparison_sql import build_sql_test_comparison_sql
from tests.unit.src.sqlbuild.cli.commands.main.compile._test_types import (
    TargetWriterCacheTestCase,
    TargetWriterTestCase,
)
from tests.unit.src.sqlbuild.cli.commands.main.compile.helpers import (
    build_cached_target_writer_project,
    build_static_target_writer_project,
    build_target_writer_plan_output,
    read_target_files,
)


@pytest.mark.parametrize(
    "test_case",
    [
        TargetWriterTestCase(
            description="writes compiled SQL, manifest, audits, and chain tests",
            expected_files={
                "compiled/models/staging/orders.sql": "SELECT 1 AS order_id\n",
                "compiled/functions/sql/is_completed_order.sql": (
                    "CREATE OR REPLACE MACRO analytics.is_completed_order(order_status) AS (\n"
                    "order_status = 'completed'\n"
                    ")\n"
                ),
                "compiled/functions/python/is_completed_order_py.sql": (
                    "REGISTER PYTHON FUNCTION analytics.is_completed_order_py"
                    "(VARCHAR) RETURNS BOOLEAN\n"
                ),
                "compiled/audits/generic/orders/not_null__order_id.sql": (
                    "SELECT order_id FROM analytics.orders WHERE order_id IS NULL\n"
                ),
            },
            expected_summary_line="Compiled 1 model, 1 seed, 2 functions, 1 audit, 1 test",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_plan_output_when_writing_target_then_expected_files_are_written(
    test_case: TargetWriterTestCase,
    tmp_path: Path,
) -> None:
    plan_output: PlanOutput = build_target_writer_plan_output()
    expected_test_sql: str = (
        build_sql_test_comparison_sql(test_entry=plan_output.test_entries[0]) + "\n"
    )
    manifest: dict[str, object] = {"metadata": {"project_name": "demo"}}

    expected_files: dict[str, str] = dict(test_case.expected_files)
    expected_files["compiled/tests/_chain_/orders__stg_orders/orders_chain.sql"] = expected_test_sql

    written: WrittenTarget = write_compile_target(
        target_dir=tmp_path / "target",
        adapter=DuckDbAdapter(),
        plan_output=plan_output,
        manifest=manifest,
    )
    manifest_path: Path = tmp_path / "target" / "manifest.json"
    unchanged_mtime_ns: int = 1_000_000_000
    os.utime(manifest_path, ns=(unchanged_mtime_ns, unchanged_mtime_ns))
    _ = write_compile_target(
        target_dir=tmp_path / "target",
        adapter=DuckDbAdapter(),
        plan_output=plan_output,
        manifest=manifest,
    )

    assert written.summary_line() == test_case.expected_summary_line
    assert read_target_files(tmp_path / "target", expected_files) == expected_files
    assert json.loads(manifest_path.read_text()) == manifest
    assert manifest_path.stat().st_mtime_ns == unchanged_mtime_ns
    assert not (tmp_path / "target" / "run").exists()


@pytest.mark.parametrize(
    "test_case",
    (
        TargetWriterTestCase(
            description="long chain uses a bounded deterministic artifact directory",
            model_count=20,
            expected_max_component_bytes=200,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_long_test_chain_when_writing_target_then_artifact_component_is_bounded(
    test_case: TargetWriterTestCase,
    tmp_path: Path,
) -> None:
    plan_output: PlanOutput = build_target_writer_plan_output()
    template: SqlTestPlanEntry = plan_output.test_entries[0]
    long_entry: SqlTestPlanEntry = replace(
        template,
        chain=tuple(
            ChainStep(
                model_name=f"model_{index:02d}_{'x' * 40}",
                resolved_sql="SELECT 1 AS value",
            )
            for index in range(test_case.model_count)
        ),
    )

    _ = write_compile_target(
        target_dir=tmp_path / "target",
        adapter=DuckDbAdapter(),
        plan_output=replace(plan_output, test_entries=(long_entry,)),
    )

    artifact: Path = next((tmp_path / "target" / "compiled" / "tests").rglob("*.sql"))
    assert len(artifact.parent.name.encode()) <= test_case.expected_max_component_bytes
    assert artifact.parent.name.startswith("model_00_")
    assert f"model_{test_case.model_count - 1:02d}_" in artifact.parent.name


@pytest.mark.parametrize(
    "test_case",
    [
        TargetWriterTestCase(
            description="writes SQL test cases to source and block scoped paths",
            expected_files={
                "compiled/tests/tests/unit/orders/block_1__small.sql": "",
                "compiled/tests/tests/unit/orders/block_1__large.sql": "",
            },
        )
    ],
    ids=lambda case: case.description,
)
def test_given_parameterized_test_entries_when_writing_target_then_case_artifacts_do_not_collide(
    test_case: TargetWriterTestCase,
    tmp_path: Path,
) -> None:
    plan_output: PlanOutput = build_target_writer_plan_output()
    template: SqlTestPlanEntry = plan_output.test_entries[0]
    case_entries: tuple[SqlTestPlanEntry, ...] = tuple(
        replace(
            template,
            key=replace(template.key, name=f"orders [{case_name}]"),
            name=f"orders [{case_name}]",
            source_path=Path("tests/unit/orders.sql"),
            block_index=1,
            parent_name="orders",
            case_name=case_name,
        )
        for case_name in ("small", "large")
    )
    parameterized_plan: PlanOutput = replace(plan_output, test_entries=case_entries)

    write_compile_target(
        target_dir=tmp_path / "target",
        adapter=DuckDbAdapter(),
        plan_output=parameterized_plan,
    )

    expected_path: str
    for expected_path in test_case.expected_files:
        assert (tmp_path / "target" / expected_path).is_file()


@pytest.mark.parametrize(
    "test_case",
    [
        TargetWriterTestCase(
            description="writes offline compiled SQL without manifest by default",
            expected_files={
                "compiled/models/staging/orders.sql": "SELECT 2 AS order_id\n",
                "compiled/functions/sql/is_completed_order.sql": (
                    "CREATE OR REPLACE MACRO analytics.is_completed_order(order_status) AS (\n"
                    "order_status = 'completed'\n"
                    ")\n"
                ),
            },
            expected_summary_line="Compiled 1 model, 1 function",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_compiled_project_when_writing_static_target_then_expected_files_are_written(
    test_case: TargetWriterTestCase,
    tmp_path: Path,
) -> None:
    project: CompiledProject = build_static_target_writer_project()
    target_dir: Path = tmp_path / "target"
    stale_path: Path = target_dir / "compiled" / "models" / "deleted.sql"
    stale_path.parent.mkdir(parents=True)
    stale_path.write_text("SELECT 'stale'\n", encoding="utf-8")

    written: WrittenTarget = write_static_compile_target(
        target_dir=target_dir,
        adapter=DuckDbAdapter(),
        project=project,
    )
    model_path: Path = target_dir / "compiled" / "models" / "staging" / "orders.sql"
    unchanged_mtime_ns: int = 1_000_000_000
    os.utime(model_path, ns=(unchanged_mtime_ns, unchanged_mtime_ns))
    _ = write_static_compile_target(
        target_dir=target_dir,
        adapter=DuckDbAdapter(),
        project=project,
    )

    assert written.summary_line() == test_case.expected_summary_line
    assert read_target_files(target_dir, test_case.expected_files) == test_case.expected_files
    assert model_path.stat().st_mtime_ns == unchanged_mtime_ns
    assert not stale_path.exists()
    assert not (target_dir / "manifest.json").exists()

    changed_project: CompiledProject = replace(
        project,
        models=(replace(project.models[0], query_sql="SELECT 3 AS order_id"),),
    )
    _ = write_static_compile_target(
        target_dir=target_dir,
        adapter=DuckDbAdapter(),
        project=changed_project,
    )

    assert model_path.read_text(encoding="utf-8") == "SELECT 3 AS order_id\n"
    assert model_path.stat().st_mtime_ns != unchanged_mtime_ns


@pytest.mark.parametrize(
    "test_case",
    (TargetWriterCacheTestCase(description="unchanged artifact reuse", expected_builder_calls=0),),
    ids=lambda case: case.description,
)
def test_given_unchanged_test_artifact_when_writing_again_then_skips_test_plan_reconstruction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    test_case: TargetWriterCacheTestCase,
) -> None:
    target_dir: Path = tmp_path / "target"
    project: CompiledProject = build_cached_target_writer_project(target_dir=target_dir)
    _ = write_static_compile_target(
        target_dir=target_dir,
        adapter=DuckDbAdapter(),
        project=project,
    )
    artifact_path: Path = next((target_dir / "compiled" / "tests").rglob("*.sql"))
    original_mtime_ns: int = artifact_path.stat().st_mtime_ns
    builder_spy: Mock = Mock(wraps=target_writer_module.build_sql_test_plan_entry)
    monkeypatch.setattr(target_writer_module, "build_sql_test_plan_entry", builder_spy)

    _ = write_static_compile_target(
        target_dir=target_dir,
        adapter=DuckDbAdapter(),
        project=project,
    )

    assert artifact_path.stat().st_mtime_ns == original_mtime_ns
    assert builder_spy.call_count == test_case.expected_builder_calls


@pytest.mark.parametrize(
    "test_case",
    (
        TargetWriterCacheTestCase(
            description="model closure invalidation", expected_builder_calls=1
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_changed_model_in_test_closure_when_writing_then_rebuilds_test_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    test_case: TargetWriterCacheTestCase,
) -> None:
    target_dir: Path = tmp_path / "target"
    project: CompiledProject = build_cached_target_writer_project(target_dir=target_dir)
    _ = write_static_compile_target(
        target_dir=target_dir,
        adapter=DuckDbAdapter(),
        project=project,
    )
    builder_spy: Mock = Mock(wraps=target_writer_module.build_sql_test_plan_entry)
    monkeypatch.setattr(target_writer_module, "build_sql_test_plan_entry", builder_spy)
    changed_project: CompiledProject = replace(
        project,
        models=(replace(project.models[0], query_sql="SELECT 3 AS order_id"),),
    )

    _ = write_static_compile_target(
        target_dir=target_dir,
        adapter=DuckDbAdapter(),
        project=changed_project,
    )

    assert builder_spy.call_count == test_case.expected_builder_calls


@pytest.mark.parametrize(
    "test_case",
    (TargetWriterCacheTestCase(description="unrelated model reuse", expected_builder_calls=0),),
    ids=lambda case: case.description,
)
def test_given_changed_unrelated_model_when_writing_then_reuses_test_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    test_case: TargetWriterCacheTestCase,
) -> None:
    target_dir: Path = tmp_path / "target"
    project: CompiledProject = build_cached_target_writer_project(target_dir=target_dir)
    _ = write_static_compile_target(
        target_dir=target_dir,
        adapter=DuckDbAdapter(),
        project=project,
    )
    unrelated_model: CompiledModel = replace(
        project.models[0],
        key=replace(project.models[0].key, name="unrelated"),
        name="unrelated",
        relative_path=Path("models/unrelated.sql"),
        query_sql="SELECT 9 AS unrelated_id",
    )
    changed_project: CompiledProject = replace(
        project,
        models=(*project.models, unrelated_model),
    )
    builder_spy: Mock = Mock(wraps=target_writer_module.build_sql_test_plan_entry)
    monkeypatch.setattr(target_writer_module, "build_sql_test_plan_entry", builder_spy)

    _ = write_static_compile_target(
        target_dir=target_dir,
        adapter=DuckDbAdapter(),
        project=changed_project,
    )
    assert builder_spy.call_count == test_case.expected_builder_calls


@pytest.mark.parametrize(
    "test_case",
    (TargetWriterCacheTestCase(description="test SQL invalidation", expected_builder_calls=1),),
    ids=lambda case: case.description,
)
def test_given_changed_test_sql_when_writing_then_rebuilds_test_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    test_case: TargetWriterCacheTestCase,
) -> None:
    target_dir: Path = tmp_path / "target"
    project: CompiledProject = build_cached_target_writer_project(target_dir=target_dir)
    _ = write_static_compile_target(
        target_dir=target_dir,
        adapter=DuckDbAdapter(),
        project=project,
    )
    builder_spy: Mock = Mock(wraps=target_writer_module.build_sql_test_plan_entry)
    monkeypatch.setattr(target_writer_module, "build_sql_test_plan_entry", builder_spy)
    changed_test: CompiledSqlTest = replace(
        project.sql_tests[0], sql_body=project.sql_tests[0].sql_body + "\n-- edit"
    )

    _ = write_static_compile_target(
        target_dir=target_dir,
        adapter=DuckDbAdapter(),
        project=replace(project, sql_tests=(changed_test,)),
    )

    assert builder_spy.call_count == test_case.expected_builder_calls


@pytest.mark.parametrize(
    "test_case",
    (
        TargetWriterCacheTestCase(
            description="compile target invalidation", expected_builder_calls=1
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_changed_compile_target_when_writing_then_rebuilds_test_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    test_case: TargetWriterCacheTestCase,
) -> None:
    target_dir: Path = tmp_path / "target"
    project: CompiledProject = build_cached_target_writer_project(target_dir=target_dir)
    _ = write_static_compile_target(
        target_dir=target_dir,
        adapter=DuckDbAdapter(),
        project=project,
    )
    builder_spy: Mock = Mock(wraps=target_writer_module.build_sql_test_plan_entry)
    monkeypatch.setattr(target_writer_module, "build_sql_test_plan_entry", builder_spy)

    _ = write_static_compile_target(
        target_dir=target_dir,
        adapter=DuckDbAdapter(),
        project=replace(project, effective_target_schema="changed_schema"),
    )

    assert builder_spy.call_count == test_case.expected_builder_calls


@pytest.mark.parametrize(
    "test_case",
    (TargetWriterCacheTestCase(description="disabled cache rebuild", expected_builder_calls=2),),
    ids=lambda case: case.description,
)
def test_given_compile_cache_disabled_when_writing_twice_then_rebuilds_test_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    test_case: TargetWriterCacheTestCase,
) -> None:
    target_dir: Path = tmp_path / "target"
    project: CompiledProject = replace(
        build_cached_target_writer_project(target_dir=target_dir),
        compile_cache_dir=None,
    )
    builder_spy: Mock = Mock(wraps=target_writer_module.build_sql_test_plan_entry)
    monkeypatch.setattr(target_writer_module, "build_sql_test_plan_entry", builder_spy)

    for _ in range(2):
        _ = write_static_compile_target(
            target_dir=target_dir,
            adapter=DuckDbAdapter(),
            project=project,
        )

    assert builder_spy.call_count == test_case.expected_builder_calls
    assert not (target_dir / "cache" / "compiler" / "sql-test-artifacts.json").exists()


@pytest.mark.parametrize(
    "test_case",
    (TargetWriterCacheTestCase(description="tampered artifact repair", expected_builder_calls=1),),
    ids=lambda case: case.description,
)
def test_given_modified_test_artifact_when_writing_then_rebuilds_expected_sql(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    test_case: TargetWriterCacheTestCase,
) -> None:
    target_dir: Path = tmp_path / "target"
    project: CompiledProject = build_cached_target_writer_project(target_dir=target_dir)
    _ = write_static_compile_target(
        target_dir=target_dir,
        adapter=DuckDbAdapter(),
        project=project,
    )
    artifact_path: Path = next((target_dir / "compiled" / "tests").rglob("*.sql"))
    expected_sql: str = artifact_path.read_text(encoding="utf-8")
    artifact_path.write_text("SELECT 'tampered'\n", encoding="utf-8")
    builder_spy: Mock = Mock(wraps=target_writer_module.build_sql_test_plan_entry)
    monkeypatch.setattr(target_writer_module, "build_sql_test_plan_entry", builder_spy)

    _ = write_static_compile_target(
        target_dir=target_dir,
        adapter=DuckDbAdapter(),
        project=project,
    )

    assert builder_spy.call_count == test_case.expected_builder_calls
    assert artifact_path.read_text(encoding="utf-8") == expected_sql
