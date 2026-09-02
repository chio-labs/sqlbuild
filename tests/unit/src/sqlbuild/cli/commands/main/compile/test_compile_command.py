from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from sqlbuild.cli.commands._helpers.compile import lineage as compile_lineage
from sqlbuild.cli.commands._helpers.compile import pipeline as compile_pipeline
from sqlbuild.cli.commands._helpers.compile import status as compile_status
from sqlbuild.cli.commands.main.project._compile import run_compile
from sqlbuild.cli.commands.models import CompileCommandRequest
from sqlbuild.cli.commands.types import CompileLineageMode
from sqlbuild.compiler.lineage.types import ColumnLineageMode
from sqlbuild.compiler.pipeline.models import ProjectGraph
from tests.unit.src.sqlbuild.cli.commands.main.compile._test_types import (
    CompileColumnContractModeTestCase,
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


@pytest.mark.parametrize(
    "test_case",
    [
        CompileCommandTestCase(
            description="compiles local project without connecting",
            expected_exit_code=0,
            expected_stdout_fragments=(
                "Compile ready  1 model",
                "orders                   OK   1 columns",
                "\u2713 Project compiled  1 model, 0 seeds, 0 functions, 0 errors, 0 warnings",
                "  Wrote: target/compiled/",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_local_project_when_running_compile_then_it_does_not_connect(
    test_case: CompileCommandTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project_dir: Path = prepare_static_compile_project(tmp_path)
    monkeypatch.setattr(
        compile_pipeline,
        "resolve_adapter",
        lambda *args, **kwargs: NoConnectDuckDbAdapter(),
    )

    exit_code: int = run_compile(
        CompileCommandRequest(project_dir=project_dir, no_sql_validation=True)
    )
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
    ids=lambda case: case.description,
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
        compile_pipeline,
        "resolve_adapter",
        lambda *args, **kwargs: NoConnectDuckDbAdapter(),
    )

    exit_code: int = run_compile(
        CompileCommandRequest(project_dir=project_dir, no_sql_validation=True)
    )

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
    ids=lambda case: case.description,
)
def test_given_dag_flag_when_running_compile_then_writes_dag_artifact(
    test_case: CompileDagArtifactTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir: Path = prepare_static_compile_project(tmp_path)
    monkeypatch.setattr(
        compile_pipeline,
        "resolve_adapter",
        lambda *args, **kwargs: NoConnectDuckDbAdapter(),
    )

    exit_code: int = run_compile(
        CompileCommandRequest(
            project_dir=project_dir,
            no_sql_validation=True,
            dag_path=test_case.dag_path,
        )
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
    ids=lambda case: case.description,
)
def test_given_python_project_dag_flag_when_running_compile_then_writes_python_dag_artifact(
    test_case: CompilePythonDagArtifactTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir: Path = prepare_python_compile_project(tmp_path)
    monkeypatch.setattr(
        compile_pipeline,
        "resolve_adapter",
        lambda *args, **kwargs: NoConnectDuckDbAdapter(),
    )

    exit_code: int = run_compile(
        CompileCommandRequest(
            project_dir=project_dir,
            no_sql_validation=True,
            dag_path=test_case.dag_path,
        )
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
    (
        CompileCommandTestCase(
            description="returns one when contract diagnostics have errors",
            expected_exit_code=1,
            expected_stdout_fragments=(
                "Compile ready  1 model",
                "orders                   FAIL 1 columns",
                "error[K001]: declared column 'customer_id' was not found in statically inferred output",
                "  model: orders",
                "  --> models/orders.sql:5:5",
                "  5 |     customer_id (),",
                "    |     ^^^^^^^^^^^",
                'settings.column_contract_mode is "implicit" (the default)',
                'column_contract_mode = "explicit"',
                "models with contract enforced remain validated",
                "\u2717 Project compiled  1 model, 0 seeds, 0 functions, 1 error, 0 warnings",
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
                "error[K002]: column 'amount_cents' inferred as TEXT but declared type is INTEGER",
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
        CompileCommandTestCase(
            description="reports output location for undeclared contract columns",
            expected_exit_code=1,
            expected_stdout_fragments=(
                "error[K005]: column 'customer_id' is not declared in enforced contract",
                "  --> models/orders.sql:11:3",
                " 11 |   2 AS customer_id",
                "    |   ^^^^^^^^^^^^^^^^",
                "  = help: add the column to MODEL(columns) or remove it from the SELECT list",
            ),
            model_sql=(
                "MODEL (\n"
                "  materialized view,\n"
                "  contract enforced,\n"
                "  columns (\n"
                "    order_id (type INTEGER),\n"
                "  ),\n"
                ");\n\n"
                "SELECT\n"
                "  1 AS order_id,\n"
                "  2 AS customer_id\n"
            ),
        ),
    ),
    ids=lambda case: case.description,
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
        compile_pipeline,
        "resolve_adapter",
        lambda *args, **kwargs: NoConnectDuckDbAdapter(),
    )

    exit_code: int = run_compile(
        CompileCommandRequest(project_dir=project_dir, no_sql_validation=True)
    )
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
            expected_message=(
                "declared column 'customer_id' was not found in statically inferred output "
                "for model 'orders'"
            ),
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
    ids=lambda case: case.description,
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
        compile_pipeline,
        "resolve_adapter",
        lambda *args, **kwargs: NoConnectDuckDbAdapter(),
    )

    exit_code: int = run_compile(
        CompileCommandRequest(
            project_dir=project_dir,
            no_sql_validation=True,
            json_output=True,
        )
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
    [
        CompileColumnContractModeTestCase(
            description="explicit mode retains column audit",
            mode="explicit",
            expected_audit_name="not_null",
            expected_column_name="customer_id",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_explicit_column_contract_mode_when_compiling_column_audit_then_audit_is_retained_without_contract_error(
    test_case: CompileColumnContractModeTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir: Path = prepare_static_compile_project(tmp_path)
    project_config_path: Path = project_dir / "sqlbuild_project.toml"
    project_config_path.write_text(
        project_config_path.read_text(encoding="utf-8")
        + f'\n[settings]\ncolumn_contract_mode = "{test_case.mode}"\n',
        encoding="utf-8",
    )
    (project_dir / "models" / "orders.sql").write_text(
        "MODEL (\n"
        "  materialized view,\n"
        "  columns (\n"
        "    customer_id (audits [not_null]),\n"
        "  ),\n"
        ");\n\n"
        "SELECT 1 AS order_id\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        compile_pipeline,
        "resolve_adapter",
        lambda *args, **kwargs: NoConnectDuckDbAdapter(),
    )

    exit_code: int = run_compile(
        CompileCommandRequest(project_dir=project_dir, no_sql_validation=True, dag_path="")
    )
    dag_payload: dict[str, object] = json.loads(
        (project_dir / "target" / "sqlbuild_dag.json").read_text(encoding="utf-8")
    )

    assert exit_code == 0
    assert len(dag_payload["checks"]) == 1
    assert dag_payload["checks"][0]["name"] == test_case.expected_audit_name
    assert dag_payload["checks"][0]["attached_column_name"] == test_case.expected_column_name


@pytest.mark.parametrize(
    "test_case",
    (
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
    ),
    ids=lambda case: case.description,
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
    ids=lambda case: case.description,
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
