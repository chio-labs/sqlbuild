from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from sqlbuild.cli.commands.main import compile as compile_command
from sqlbuild.cli.commands.main.compile import run_compile
from sqlbuild.cli.commands.main.helpers.compile import lineage as compile_lineage
from sqlbuild.cli.commands.main.helpers.compile import status as compile_status
from sqlbuild.cli.commands.main.helpers.compile.types import CompileLineageMode
from sqlbuild.compiler.lineage.types import ColumnLineageMode
from sqlbuild.compiler.pipeline.models import ProjectGraph
from tests.unit.src.sqlbuild.cli.commands.main.compile._test_types import (
    CompileCommandTestCase,
    CompileDagArtifactTestCase,
    CompileJsonDiagnosticsTestCase,
    CompileLineageModeTestCase,
    CompilePythonDagArtifactTestCase,
)
from tests.unit.src.sqlbuild.cli.commands.main.compile.helpers import (
    NoConnectDuckDbAdapter,
    prepare_python_compile_project,
    prepare_static_compile_project,
)

CONTRACT_DIAGNOSTIC_TEST_CASES: tuple[CompileCommandTestCase, ...] = (
    CompileCommandTestCase(
        description="returns one when contract diagnostics have errors",
        expected_exit_code=1,
        expected_stdout_fragments=(
            "Compile ready (1 model)",
            "  orders                   FAIL 1 columns",
            "error[K001]: required column 'customer_id' missing from model output",
            "  model: orders",
            "  --> models/orders.sql:5:5",
            "  5 |     customer_id (),",
            "    |     ^^^^^^^^^^^",
            "  = help: add customer_id to the SELECT list or remove it from MODEL(columns)",
            "  Compiled: 1 model, 0 seeds, 0 functions, 1 error, 0 warnings",
            "  Wrote: target/compiled/",
        ),
        model_sql=(
            "MODEL (\n"
            "  materialized view,\n"
            "  columns (\n"
            "    order_id (),\n"
            "    customer_id (),\n"
            "  ),\n"
            ");\n\n"
            "SELECT 1 AS order_id\n"
        ),
    ),
    CompileCommandTestCase(
        description="reports contract and output locations for type diagnostics",
        expected_exit_code=1,
        expected_stdout_fragments=(
            "error[K002]: column 'amount_cents' inferred as TEXT but contract declares INTEGER",
            "  --> models/orders.sql:4:5",
            "  4 |     amount_cents (type INTEGER),",
            "    |     ^^^^^^^^^^^^",
            "  output:",
            "  --> models/orders.sql:9:3",
            "  9 |   CAST('1' AS VARCHAR) AS amount_cents",
            "inferred TEXT",
            "  = help: change the declared type or cast the expression explicitly",
        ),
        model_sql=(
            "MODEL (\n"
            "  materialized view,\n"
            "  columns (\n"
            "    amount_cents (type INTEGER),\n"
            "  ),\n"
            ");\n\n"
            "SELECT\n"
            "  CAST('1' AS VARCHAR) AS amount_cents\n"
            "FROM (SELECT 1) AS source\n"
        ),
    ),
)

LINEAGE_ANALYSIS_MODE_TEST_CASES: tuple[CompileLineageModeTestCase, ...] = (
    CompileLineageModeTestCase(
        description="uses fast lineage by default",
        lineage_mode=CompileLineageMode.FAST,
        expected_lineage_mode_values=(ColumnLineageMode.FAST.value,),
    ),
    CompileLineageModeTestCase(
        description="uses rich lineage when requested",
        lineage_mode=CompileLineageMode.RICH,
        expected_lineage_mode_values=(ColumnLineageMode.RICH.value,),
    ),
)


@pytest.mark.parametrize(
    "test_case",
    [
        CompileCommandTestCase(
            description="compiles local project without connecting",
            expected_exit_code=0,
            expected_stdout_fragments=(
                "Compile ready (1 model)",
                "  orders                   OK 1 columns",
                "  Compiled: 1 model, 0 seeds, 0 functions, 0 errors, 0 warnings",
                "  Wrote: target/compiled/",
            ),
        )
    ],
    ids=["compiles local project without connecting"],
)
def test_given_local_project_when_running_compile_then_it_does_not_connect(
    test_case: CompileCommandTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project_dir: Path = prepare_static_compile_project(tmp_path)
    monkeypatch.setattr(
        compile_command,
        "resolve_adapter",
        lambda *args, **kwargs: NoConnectDuckDbAdapter(),
    )

    exit_code: int = run_compile(project_dir=project_dir, no_sql_validation=True)
    rendered_stdout: str = capsys.readouterr().out

    assert exit_code == test_case.expected_exit_code
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in rendered_stdout
    assert (project_dir / "target" / "compiled" / "models" / "orders.sql").exists()
    assert not (project_dir / "target" / "manifest.json").exists()


@pytest.mark.parametrize(
    "test_case",
    [
        CompileCommandTestCase(
            description="persists phase timings for tty stdout",
            expected_exit_code=0,
            expected_stdout_fragments=(
                "Discovered project.",
                "Compiled project graph.",
                "Analyzed column lineage.",
                "Validated model contracts.",
                "Wrote compiled artifacts.",
            ),
        )
    ],
    ids=["persists phase timings for tty stdout"],
)
def test_given_tty_stdout_when_running_compile_then_it_persists_phase_timings(
    test_case: CompileCommandTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir: Path = prepare_static_compile_project(tmp_path)
    started_messages: list[str] = []
    completed_messages: list[str] = []

    class FakeStdout:
        def isatty(self) -> bool:
            return True

        def write(self, text: str) -> int:
            return len(text)

        def flush(self) -> None:
            return None

    class FakeStatusReporter:
        def __init__(self, **kwargs: object) -> None:
            del kwargs

        def start(self, message: str) -> None:
            started_messages.append(message)

        def update(self, message: str) -> None:
            started_messages.append(message)

        def complete(self, message: str, *, blank_line_after: bool = False) -> None:
            del blank_line_after
            completed_messages.append(message)

        def close(self) -> None:
            return None

    monkeypatch.setattr(compile_status.sys, "stdout", FakeStdout())
    monkeypatch.setattr(compile_status, "TransientStatusReporter", FakeStatusReporter)
    monkeypatch.setattr(
        compile_command,
        "resolve_adapter",
        lambda *args, **kwargs: NoConnectDuckDbAdapter(),
    )

    exit_code: int = run_compile(project_dir=project_dir, no_sql_validation=True)

    assert exit_code == test_case.expected_exit_code
    assert started_messages == [
        "Discovering project...",
        "Compiling project graph...",
        "Analyzing column lineage...",
        "Validating model contracts...",
        "Writing compiled artifacts...",
    ]
    assert len(completed_messages) == len(test_case.expected_stdout_fragments)
    for index, fragment in enumerate(test_case.expected_stdout_fragments):
        assert completed_messages[index].startswith(f"{fragment} (")


@pytest.mark.parametrize(
    "test_case",
    [
        CompileDagArtifactTestCase(
            description="writes dag artifact to default target path",
            dag_path="",
            expected_project_name="offline_compile",
            expected_node_ids=("model:orders",),
        )
    ],
    ids=["writes dag artifact to default target path"],
)
def test_given_dag_flag_when_running_compile_then_writes_dag_artifact(
    test_case: CompileDagArtifactTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir: Path = prepare_static_compile_project(tmp_path)
    monkeypatch.setattr(
        compile_command,
        "resolve_adapter",
        lambda *args, **kwargs: NoConnectDuckDbAdapter(),
    )

    exit_code: int = run_compile(
        project_dir=project_dir,
        no_sql_validation=True,
        dag_path=test_case.dag_path,
    )
    dag_payload: dict[str, object] = json.loads(
        (project_dir / "target" / "sqlbuild_dag.json").read_text(encoding="utf-8")
    )

    assert exit_code == 0
    assert dag_payload["project_name"] == test_case.expected_project_name
    assert tuple(node["id"] for node in dag_payload["nodes"]) == test_case.expected_node_ids


@pytest.mark.parametrize(
    "test_case",
    [
        CompilePythonDagArtifactTestCase(
            description="writes Python nodes to default dag artifact path",
            dag_path="",
            expected_project_name="offline_compile",
            expected_node_ids={
                "model:orders",
                "task:prepare_orders",
                "loader:warehouse_export",
                "asset:orders_export",
                "check:check_orders_export",
                "check:check_loader_export",
            },
            expected_edges={
                ("model:orders", "task:prepare_orders"),
                ("task:prepare_orders", "loader:warehouse_export"),
                ("loader:warehouse_export", "asset:orders_export"),
                ("loader:warehouse_export", "check:check_loader_export"),
            },
            expected_check_ids={
                "check:check_orders_export",
                "check:check_loader_export",
            },
        )
    ],
    ids=["writes Python nodes to default dag artifact path"],
)
def test_given_python_project_dag_flag_when_running_compile_then_writes_python_dag_artifact(
    test_case: CompilePythonDagArtifactTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir: Path = prepare_python_compile_project(tmp_path)
    monkeypatch.setattr(
        compile_command,
        "resolve_adapter",
        lambda *args, **kwargs: NoConnectDuckDbAdapter(),
    )

    exit_code: int = run_compile(
        project_dir=project_dir,
        no_sql_validation=True,
        dag_path=test_case.dag_path,
    )
    dag_payload: dict[str, object] = json.loads(
        (project_dir / "target" / "sqlbuild_dag.json").read_text(encoding="utf-8")
    )
    node_ids: set[str] = {str(node["id"]) for node in dag_payload["nodes"]}
    edges: set[tuple[str, str]] = {
        (str(edge["from_id"]), str(edge["to_id"])) for edge in dag_payload["edges"]
    }
    check_ids: set[str] = {str(check["id"]) for check in dag_payload["checks"]}

    assert exit_code == 0
    assert dag_payload["project_name"] == test_case.expected_project_name
    assert test_case.expected_node_ids.issubset(node_ids)
    assert test_case.expected_edges.issubset(edges)
    assert test_case.expected_check_ids.issubset(check_ids)


@pytest.mark.parametrize(
    "test_case",
    CONTRACT_DIAGNOSTIC_TEST_CASES,
    ids=[case.description for case in CONTRACT_DIAGNOSTIC_TEST_CASES],
)
def test_given_contract_errors_when_running_compile_then_reports_diagnostics(
    test_case: CompileCommandTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project_dir: Path = prepare_static_compile_project(tmp_path)
    assert test_case.model_sql is not None
    (project_dir / "models" / "orders.sql").write_text(
        test_case.model_sql,
        encoding="utf-8",
    )
    monkeypatch.setattr(
        compile_command,
        "resolve_adapter",
        lambda *args, **kwargs: NoConnectDuckDbAdapter(),
    )

    exit_code: int = run_compile(project_dir=project_dir, no_sql_validation=True)
    rendered_stdout: str = capsys.readouterr().out

    assert exit_code == test_case.expected_exit_code
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in rendered_stdout
    assert (project_dir / "target" / "compiled" / "models" / "orders.sql").exists()
    assert not (project_dir / "target" / "manifest.json").exists()


@pytest.mark.parametrize(
    "test_case",
    [
        CompileJsonDiagnosticsTestCase(
            description="serializes contract diagnostics in compile json",
            expected_exit_code=1,
            expected_code="K001",
            expected_severity="error",
            expected_message="required column 'customer_id' missing from model output",
            expected_line=5,
            expected_column=5,
            model_sql=(
                "MODEL (\n"
                "  materialized view,\n"
                "  columns (\n"
                "    order_id (),\n"
                "    customer_id (),\n"
                "  ),\n"
                ");\n\n"
                "SELECT 1 AS order_id\n"
            ),
        )
    ],
    ids=["serializes contract diagnostics in compile json"],
)
def test_given_contract_errors_when_running_compile_json_then_serializes_diagnostics(
    test_case: CompileJsonDiagnosticsTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project_dir: Path = prepare_static_compile_project(tmp_path)
    (project_dir / "models" / "orders.sql").write_text(
        test_case.model_sql,
        encoding="utf-8",
    )
    monkeypatch.setattr(
        compile_command,
        "resolve_adapter",
        lambda *args, **kwargs: NoConnectDuckDbAdapter(),
    )

    exit_code: int = run_compile(
        project_dir=project_dir,
        no_sql_validation=True,
        json_output=True,
    )
    payload: dict[str, object] = json.loads(capsys.readouterr().out)
    diagnostics: list[dict[str, object]] = payload["diagnostics"]

    assert exit_code == test_case.expected_exit_code
    assert payload["has_errors"] is True
    assert payload["summary"]["errors"] == 1
    assert diagnostics[0]["code"] == test_case.expected_code
    assert diagnostics[0]["severity"] == test_case.expected_severity
    assert diagnostics[0]["message"] == test_case.expected_message
    assert diagnostics[0]["path"] == "models/orders.sql"
    assert diagnostics[0]["line"] == test_case.expected_line
    assert diagnostics[0]["column"] == test_case.expected_column
    assert diagnostics[0]["location"] == {
        "path": "models/orders.sql",
        "line": test_case.expected_line,
        "column": test_case.expected_column,
        "end_line": test_case.expected_line,
        "end_column": 16,
    }
    assert diagnostics[0]["phase"] == "contract"


@pytest.mark.parametrize(
    "test_case",
    LINEAGE_ANALYSIS_MODE_TEST_CASES,
    ids=[case.description for case in LINEAGE_ANALYSIS_MODE_TEST_CASES],
)
def test_given_lineage_mode_when_resolving_compile_analysis_then_returns_expected_mode(
    test_case: CompileLineageModeTestCase,
) -> None:
    mode: ColumnLineageMode = compile_lineage.compile_analysis_lineage_mode(test_case.lineage_mode)

    assert (mode.value,) == test_case.expected_lineage_mode_values


@pytest.mark.parametrize(
    "test_case",
    [
        CompileLineageModeTestCase(
            description="skips lineage when disabled",
            lineage_mode=CompileLineageMode.NONE,
            expected_lineage_mode_values=(),
        )
    ],
    ids=["skips lineage when disabled"],
)
def test_given_lineage_disabled_when_building_compile_lineage_then_skips_analyzer(
    test_case: CompileLineageModeTestCase,
) -> None:
    lineage: object = compile_lineage.build_compile_lineage(
        graph=cast(ProjectGraph, object()),
        dialect=None,
        mode=test_case.lineage_mode,
    )

    assert lineage is None
    assert test_case.expected_lineage_mode_values == ()
