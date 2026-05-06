from __future__ import annotations

import json
from pathlib import Path

import pytest

from sqlbuild.cli.commands.main import compile as compile_command
from sqlbuild.cli.commands.main.compile import run_compile
from tests.unit.src.sqlbuild.cli.commands.main.compile._test_types import (
    CompileCommandTestCase,
    CompileJsonDiagnosticsTestCase,
)
from tests.unit.src.sqlbuild.cli.commands.main.compile.helpers import (
    NoConnectDuckDbAdapter,
    prepare_static_compile_project,
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
            description="returns one when contract diagnostics have errors",
            expected_exit_code=1,
            expected_stdout_fragments=(
                "Compile ready (1 model)",
                "  orders                   FAIL 1 columns",
                "error[K001]: required column 'customer_id' missing from model output",
                "  model: orders",
                "  file: models/orders.sql",
                "  help: add customer_id to the SELECT list or remove it from MODEL(columns)",
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
    ],
    ids=["reports contract diagnostics"],
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
    assert diagnostics[0]["phase"] == "contract"
