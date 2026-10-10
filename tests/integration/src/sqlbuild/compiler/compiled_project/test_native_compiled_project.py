"""The rules request reads model facts the compile-input stage retained natively."""

import json
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.cli.entry.main.entry import main
from tests.integration.src.sqlbuild.compiler.compiled_project._test_types import (
    RetainedRulesRowsTestCase,
    UnretainedRulesRowsTestCase,
)
from tests.integration.src.sqlbuild.compiler.compiled_project.helpers import (
    TYPE_PROOF_FILES,
    forbid_hand_built_projects,
    skip_model_retention,
)
from tests.integration.src.sqlbuild.compiler.graph.helpers import write_files


@pytest.mark.parametrize(
    "test_case",
    [
        RetainedRulesRowsTestCase(
            description="default engine proves the passthrough from retained facts",
            engine="native",
            expected_codes=("K002", "SQBRCONTRACT105"),
        ),
        RetainedRulesRowsTestCase(
            description="python engine reads the same retained facts",
            engine="python",
            expected_codes=("K002", "SQBRCONTRACT105"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_compiled_project_when_evaluating_rules_then_retained_model_facts_are_read(
    test_case: RetainedRulesRowsTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_files(project_dir=tmp_path, files=TYPE_PROOF_FILES)
    forbid_hand_built_projects(monkeypatch=monkeypatch, engine=test_case.engine)

    _ = main(["--project-dir", str(tmp_path), "compile", "--json", "--no-cache"])
    payload: dict[str, Any] = json.loads(capsys.readouterr().out)

    assert tuple(item["code"] for item in payload["diagnostics"]) == test_case.expected_codes


@pytest.mark.parametrize(
    "test_case",
    [
        UnretainedRulesRowsTestCase(
            description="models the compile-input stage did not retain",
            expected_error="compiled model 'orders' has no retained compile facts",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unretained_model_facts_when_evaluating_rules_then_compile_reports_it(
    test_case: UnretainedRulesRowsTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_files(project_dir=tmp_path, files=TYPE_PROOF_FILES)
    skip_model_retention(monkeypatch=monkeypatch)

    exit_code: int = main(["--project-dir", str(tmp_path), "compile", "--no-cache"])
    output: str = "".join(capsys.readouterr())

    assert exit_code == 1
    assert test_case.expected_error in output


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
