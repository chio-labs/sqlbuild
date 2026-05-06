from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.cli.commands.main import compile as compile_command
from sqlbuild.cli.commands.main.compile import run_compile
from tests.unit.src.sqlbuild.cli.commands.main.compile._test_types import (
    CompileCommandTestCase,
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
