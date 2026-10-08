"""Engine parity for the declaration scope the native engine builds: index, lookup and grants."""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from tests.integration.src.sqlbuild.compiler.helpers import mismatches
from tests.integration.src.sqlbuild.compiler.scopes._test_types import (
    GeneratedScopeParityTestCase,
    ScopeCommandParityTestCase,
    ScopeEngineParityTestCase,
    ScopeEngineTierTestCase,
)
from tests.integration.src.sqlbuild.compiler.scopes.helpers import (
    SCOPED_PROJECT,
    ScopeOutcome,
    generated_scope_files,
    native_scope_attempts,
    scope_command_indexes,
    scope_engine_outcomes,
    write_project,
)

_BROKEN_TEST: str = (
    'TEST (name "broken");\n\nWITH\n__source__raw_orders AS (\n  SELECT 1\n),\n'
    "__expected__ AS (\n  SELECT 1\n)\nSELECT 1\n"
)

_SCENARIO_HEADER: str = 'SCENARIO (\n  description "Flow"\n);\n\n'
_MACRO_TEST_HEADER: str = 'TEST (mode macro, name "eu_label");\n\n'


@pytest.mark.parametrize(
    "test_case",
    [
        ScopeEngineParityTestCase(
            description="nested scoped roots, private values, expected-model and macro-test grants",
            files=SCOPED_PROJECT,
            expected_minimum_grants=5,
        ),
        ScopeEngineParityTestCase(
            description="a global enum duplicating a scoped enum fails with Python's diagnostics",
            files={
                **SCOPED_PROJECT,
                "enums/region.sql": "ENUM (name eu_region, members [EAST]);\n",
            },
            expected_error="Duplicate declaration 'enum:eu_region'",
        ),
        ScopeEngineParityTestCase(
            description="a malformed expected-model CTE fails with Python's relationship fault",
            files={**SCOPED_PROJECT, "tests/unit/test_broken.sql": _BROKEN_TEST},
            expected_error="__expected__",
        ),
        ScopeEngineParityTestCase(
            description="a scenario's bare expected prefix fails with Python's scenario fault",
            files={
                **SCOPED_PROJECT,
                "tests/scenarios/flow.sql": _SCENARIO_HEADER
                + "WITH\n__source__raw_orders AS (SELECT 1),\n__expected__ AS (SELECT 1)\n",
            },
            expected_error=(
                "SQL scenario 'tests/scenarios/flow.sql' must use __expected__<model> to "
                "identify a target"
            ),
        ),
        ScopeEngineParityTestCase(
            description="the first of several broken tests and scenarios is reported",
            files={
                **SCOPED_PROJECT,
                "tests/unit/test_a_missing_as.sql": 'TEST (name "a");\n\nWITH\n'
                "__source__raw_orders (SELECT 1),\n__expected__orders AS (SELECT 1)\n",
                "tests/unit/test_b_broken.sql": _BROKEN_TEST,
                "tests/scenarios/flow.sql": _SCENARIO_HEADER
                + "WITH\n__source__raw_orders AS (SELECT 1\n",
            },
            expected_error="SQL test 'tests/unit/test_a_missing_as.sql' expected keyword AS",
        ),
        ScopeEngineParityTestCase(
            description="a macro test whose CTE scan fails reports Python's scanner error",
            files={
                **SCOPED_PROJECT,
                "tests/unit/test_eu_label.sql": _MACRO_TEST_HEADER
                + "WITH\n__macro_actual__ AS SELECT @eu_label('1') AS label\n",
            },
            expected_error="SQL test 'tests/unit/test_eu_label.sql' CTE '__macro_actual__' must",
        ),
        ScopeEngineParityTestCase(
            description="a macro test only Polyglot reads keeps Python's fallback",
            files={
                **SCOPED_PROJECT,
                "tests/unit/test_eu_label.sql": _MACRO_TEST_HEADER
                + "WITH\n__macro_actual__ AS MATERIALIZED (\n  SELECT @cents('1') AS label\n),\n"
                "__macro_expected__ AS (\n  SELECT 100 AS label\n)\nSELECT 1\n",
            },
        ),
        ScopeEngineParityTestCase(
            description="non-ASCII folders keep Python's repr order of path keys",
            files={
                **SCOPED_PROJECT,
                "models/sales/r\u00e9gion/regional.sql": (
                    'MODEL (\n  description "Regional",\n);\n\n'
                    'SELECT order_id, @const("sales_cap") AS cap\nFROM __ref("orders")\n'
                ),
            },
            expected_minimum_grants=5,
        ),
        ScopeEngineParityTestCase(
            description="a test granted a deeper macro's folder through a macro test",
            files={
                **SCOPED_PROJECT,
                "models/sales/eu/_macros/rates.py": (
                    'def eu_rate(value: str) -> str:\n    return f"{value} * 2"\n\n\n'
                    "def eu_label(value: str) -> str:\n    return eu_rate(value)\n"
                ),
                "tests/unit/test_eu_label.sql": (
                    'TEST (mode macro, name "eu_label");\n\nWITH\n'
                    "__macro_actual__ AS (\n  SELECT @eu_label('1') AS label\n),\n"
                    "__macro_expected__ AS (\n  SELECT 1 * 2 AS label\n)\nSELECT 1\n"
                ),
            },
            expected_minimum_grants=8,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_scoped_project_when_building_scope_under_each_engine_then_outcomes_match(
    test_case: ScopeEngineParityTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_project(project_dir=tmp_path, files=test_case.files)

    python, native, built = scope_engine_outcomes(project_dir=tmp_path, monkeypatch=monkeypatch)

    assert (
        native == python,
        built,
        (python.kind == "error") == bool(test_case.expected_error),
        test_case.expected_error in python.error,
        native.grants >= test_case.expected_minimum_grants,
    ) == (True, True, True, True, True), test_case.description


@pytest.mark.parametrize(
    "test_case",
    [
        GeneratedScopeParityTestCase(
            description="seeded scoped declarations, grants and relationship faults",
            seed=20261007,
            count=120,
            expected_minimum_valid=40,
            expected_minimum_invalid=10,
            expected_minimum_granting=15,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_generated_scoped_projects_when_building_scope_then_engines_match(
    test_case: GeneratedScopeParityTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rng: random.Random = random.Random(test_case.seed)
    project_dirs: list[Path] = [tmp_path / f"project_{index}" for index in range(test_case.count)]
    for project_dir in project_dirs:
        write_project(project_dir=project_dir, files=generated_scope_files(rng=rng))

    outcomes: list[tuple[ScopeOutcome, ScopeOutcome, bool]] = [
        scope_engine_outcomes(project_dir=project_dir, monkeypatch=monkeypatch)
        for project_dir in project_dirs
    ]

    python: list[ScopeOutcome] = [outcome[0] for outcome in outcomes]
    native: list[ScopeOutcome] = [outcome[1] for outcome in outcomes]
    assert (
        mismatches(
            inputs=[path.name for path in project_dirs],
            expected=[*python],
            actual=[*native],
        ),
        all(outcome[2] for outcome in outcomes),
        sum(item.kind == "ok" for item in python) >= test_case.expected_minimum_valid,
        sum(item.kind == "error" for item in python) >= test_case.expected_minimum_invalid,
        sum(item.grants > 0 for item in python) >= test_case.expected_minimum_granting,
    ) == (list(test_case.expected_mismatches), True, True, True, True), test_case.description


@pytest.mark.parametrize(
    "test_case",
    [
        ScopeCommandParityTestCase(
            description="the offline scope command index with compile usages and grants",
            files=SCOPED_PROJECT,
            expected_minimum_grants=5,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_scoped_project_when_scope_command_builds_index_then_engines_match(
    test_case: ScopeCommandParityTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_project(project_dir=tmp_path, files=test_case.files)

    python, native = scope_command_indexes(project_dir=tmp_path, monkeypatch=monkeypatch)

    assert (native == python, len(native.grants) >= test_case.expected_minimum_grants) == (
        True,
        True,
    ), test_case.description


@pytest.mark.parametrize(
    "test_case",
    [
        ScopeEngineTierTestCase(
            description="python oracle", engine="python", expected_native_attempts=0
        ),
        ScopeEngineTierTestCase(
            description="shipped native stages only", engine="native", expected_native_attempts=0
        ),
        ScopeEngineTierTestCase(
            description="native preview", engine="native-preview", expected_native_attempts=1
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_engine_tier_when_building_scope_then_native_scopes_run_only_in_preview(
    test_case: ScopeEngineTierTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_project(project_dir=tmp_path, files=SCOPED_PROJECT)

    attempts, outcome = native_scope_attempts(
        project_dir=tmp_path, engine=test_case.engine, monkeypatch=monkeypatch
    )

    assert (attempts, outcome.kind) == (test_case.expected_native_attempts, "ok")


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
