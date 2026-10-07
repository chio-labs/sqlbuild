"""Engine parity for SQL unit-test and scenario files discovered natively."""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from tests.integration.src.sqlbuild.compiler.discovery._test_types import (
    EngineSwitchParityTestCase,
    GeneratedSqlTestParityTestCase,
)
from tests.integration.src.sqlbuild.compiler.discovery.helpers import (
    generated_scenario_bytes,
    generated_test_bytes,
    sql_test_discovery_outcome,
    stage_outcome,
    write_project,
)
from tests.integration.src.sqlbuild.compiler.helpers import mismatches

_TEST: bytes = b'TEST (name "keeps_orders");\n\nSELECT 1\n'
_SCENARIO: bytes = b'SCENARIO (description "Orders world");\n\nSELECT 1\n'


@pytest.mark.parametrize(
    "test_case",
    [
        GeneratedSqlTestParityTestCase(
            description="seeded test blocks and scenario headers",
            seed=71,
            case_count=1000,
            expected_minimum_parsed=80,
            expected_minimum_failed=150,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_generated_test_files_when_discovering_with_each_engine_then_outcomes_match(
    test_case: GeneratedSqlTestParityTestCase, tmp_path: Path
) -> None:
    rng: random.Random = random.Random(test_case.seed)
    files: list[tuple[tuple[str, bytes], ...]] = [
        (
            ("tests/unit/orders.sql", generated_test_bytes(rng=rng)),
            ("tests/scenarios/orders.sql", generated_scenario_bytes(rng=rng)),
        )
        for _ in range(test_case.case_count)
    ]
    project_dirs: list[Path] = [tmp_path / f"case_{index}" for index in range(len(files))]
    for project_dir, project_files in zip(project_dirs, files, strict=True):
        write_project(project_dir=project_dir, files=project_files)
    expected: list[object] = [
        sql_test_discovery_outcome(project_dir=project_dir, native=False)
        for project_dir in project_dirs
    ]

    actual: list[object] = [
        sql_test_discovery_outcome(project_dir=project_dir, native=True)
        for project_dir in project_dirs
    ]

    parsed: int = sum(isinstance(outcome, str) for outcome in expected)
    assert (
        mismatches(inputs=list(files), expected=expected, actual=actual),
        parsed >= test_case.expected_minimum_parsed,
        len(expected) - parsed >= test_case.expected_minimum_failed,
    ) == (list(test_case.expected_mismatches), True, True), test_case.description


@pytest.mark.parametrize(
    "test_case",
    [
        EngineSwitchParityTestCase(
            description="test and scenario files in nested, macro and scoped folders",
            files=(
                ("models/orders.sql", b'MODEL (description "Orders");\nSELECT 1 AS order_id'),
                ("tests/unit/orders.sql", _TEST),
                ("tests/unit/marts/b.sql", _TEST),
                ("tests/unit/macros/money.sql", _TEST),
                ("tests/unit/marts/_macros/helpers.py", b"def cents(value):\n    return value\n"),
                ("tests/unit/marts/_sqlbuild/enums/status.sql", b"ENUM (name s, members [A]);\n"),
                ("tests/scenarios/north/orders.sql", _SCENARIO),
                ("tests/scenarios/south.sql", _SCENARIO),
            ),
        ),
        EngineSwitchParityTestCase(
            description="the first failing test file in path order wins",
            files=(
                ("tests/unit/a.sql", _TEST),
                ("tests/unit/b.sql", b"\xff"),
                ("tests/unit/c.sql", b"TEST (nme 1);\nSELECT 1"),
            ),
        ),
        EngineSwitchParityTestCase(
            description="a semantic failure in an earlier block beats a later syntax failure",
            files=(
                ("tests/unit/a.sql", b"TEST (mode bogus);\nSELECT 1\nTEST (name ();\nSELECT 2"),
            ),
        ),
        EngineSwitchParityTestCase(
            description="an unreadable scenario fails with Python's read error",
            files=(("tests/scenarios/a.sql", b"SCENARIO ();\n\xfe"),),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_test_files_when_discovering_through_the_engine_switch_then_inputs_match(
    test_case: EngineSwitchParityTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_project(project_dir=tmp_path, files=test_case.files)
    python: object = stage_outcome(project_dir=tmp_path, engine="python", monkeypatch=monkeypatch)

    native: object = stage_outcome(project_dir=tmp_path, engine="native", monkeypatch=monkeypatch)

    assert (native == python) is test_case.expected_identical, test_case.description
