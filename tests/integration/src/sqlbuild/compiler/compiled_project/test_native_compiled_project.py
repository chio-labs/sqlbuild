"""The rules request reads model facts the compile-input stage retained natively."""

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.cli.entry.main.entry import main
from tests.integration.src.sqlbuild.compiler.compiled_project._test_types import (
    ModelLoopParityTestCase,
    RetainedRulesRowsTestCase,
    UnretainedRulesRowsTestCase,
    ZeroMaterializationTestCase,
)
from tests.integration.src.sqlbuild.compiler.compiled_project.helpers import (
    LEGACY_PROJECT_TYPES,
    PARITY_FILES,
    TYPE_PROOF_FILES,
    WAFFLE_SHOP_NATIVE_MODELS,
    build_inputs_with_native_loop,
    copy_project,
    count_legacy_constructions,
    expansions,
    forbid_hand_built_projects,
    skip_model_retention,
)
from tests.integration.src.sqlbuild.compiler.graph.helpers import ORDERS_PROJECT_FILES, write_files


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


@pytest.mark.parametrize(
    "test_case",
    [
        ModelLoopParityTestCase(
            description="plain, interpolated, seeded, incremental and attachment-bound models",
            fixtures=(),
            files=PARITY_FILES,
            expected_native_models=3,
        ),
        ModelLoopParityTestCase(
            description="neutral fixture with macros, enums and declared columns",
            fixtures=("tests/e2e/fixtures/waffle_shop",),
            files={},
            expected_native_models=WAFFLE_SHOP_NATIVE_MODELS,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_project_when_running_native_model_loop_then_inputs_and_facts_match_attachment(
    test_case: ModelLoopParityTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir: Path = copy_project(
        fixtures=test_case.fixtures, files=test_case.files, project_dir=tmp_path / "project"
    )

    native, native_counts = build_inputs_with_native_loop(
        project_dir=project_dir, native=True, monkeypatch=monkeypatch
    )
    attached, attached_counts = build_inputs_with_native_loop(
        project_dir=project_dir, native=False, monkeypatch=monkeypatch
    )

    assert native_counts == [test_case.expected_native_models]
    assert attached_counts == [0]
    assert native.model_inputs == attached.model_inputs
    assert expansions(native) == expansions(attached)
    assert native.native_project == attached.native_project


@pytest.mark.xfail(
    strict=True,
    reason="final gate: compile inputs, assembly, planner and artifacts still build Python objects",
)
@pytest.mark.parametrize(
    "test_case",
    [
        ZeroMaterializationTestCase(
            description="ordinary compile",
            arguments=("compile", "--no-cache"),
            expected_constructions=dict.fromkeys(LEGACY_PROJECT_TYPES, 0),
        ),
        ZeroMaterializationTestCase(
            description="selected compile with a JSON report",
            arguments=("compile", "--no-cache", "--json", "--select", "orders+"),
            expected_constructions=dict.fromkeys(LEGACY_PROJECT_TYPES, 0),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_ordinary_compile_when_compiling_then_no_python_project_is_constructed(
    test_case: ZeroMaterializationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_files(project_dir=tmp_path, files=ORDERS_PROJECT_FILES)
    counts: Counter[str] = count_legacy_constructions(monkeypatch=monkeypatch)

    exit_code: int = main(["--project-dir", str(tmp_path), *test_case.arguments])
    _ = capsys.readouterr()

    assert exit_code == 0
    assert {name: counts[name] for name in LEGACY_PROJECT_TYPES} == (
        test_case.expected_constructions
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
