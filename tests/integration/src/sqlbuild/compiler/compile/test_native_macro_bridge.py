"""The native macro bridge renders compile inputs byte-identically to the Python engine."""

from __future__ import annotations

import random
import sys
import unicodedata
from pathlib import Path

import pytest

from sqlbuild.compiler.macro_bridge.classes.macro_bridge import MacroBridge
from tests.integration.src.sqlbuild.compiler.compile._test_types import (
    MacroBridgeFailureTestCase,
    MacroBridgeMemoTestCase,
    MacroBridgeParityTestCase,
    MacroExpansionDifferentialTestCase,
)
from tests.integration.src.sqlbuild.compiler.compile.helpers import (
    MACRO_BRIDGE_PROJECT_FILES,
    MACRO_CALL_LOG_ENV_VAR,
    comparable_capture,
    expansion_outcome,
    random_macro_sql,
    render_compile_inputs,
    render_error,
    write_project,
)
from tests.integration.src.sqlbuild.compiler.helpers import mismatches

_FAILURE_BASE_FILES: dict[str, str] = {
    "sqlbuild_project.toml": MACRO_BRIDGE_PROJECT_FILES["sqlbuild_project.toml"],
    "macros/common.py": (
        "def cents(column: str) -> str:\n"
        '    """Convert an amount to cents."""\n'
        '    return f"{column} * 100"\n\n\n'
        "def explode(column: str) -> str:\n"
        '    """Fail while rendering."""\n'
        '    raise ValueError(f"cannot render {column}")\n\n\n'
        "def number(column: str) -> int:\n"
        '    """Return a value that is not SQL."""\n'
        "    return 1\n"
    ),
    "models/a_first.sql": (
        'MODEL (description "First");\n\nSELECT @cents("amount") AS amount_cents\n'
    ),
}


@pytest.mark.parametrize(
    "test_case",
    [
        MacroBridgeParityTestCase(
            description="nested, context, scoped, typed-reference, hook, test, audit, source "
            "and function macros",
            files=MACRO_BRIDGE_PROJECT_FILES,
            expected_fragments=(
                "'north:x'",
                "amount * 11",
                "amount * 21",
                "'base_rate, north_rate'",
                "'base_rate, south_rate'",
                "'__SQLBUILD_RELATION_0__'",
                "'__SQLBUILD_RELATION_1__'",
                "P006",
                "SELECT 2 * 100 AS stamped",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_macro_heavy_project_when_rendering_with_each_engine_then_inputs_are_identical(
    test_case: MacroBridgeParityTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir: Path = write_project(root=tmp_path / "project", files=test_case.files)

    python_capture: str = comparable_capture(
        render_compile_inputs(project_dir=project_dir, engine="python", monkeypatch=monkeypatch)
    )
    native_capture: str = comparable_capture(
        render_compile_inputs(
            project_dir=project_dir, engine="native-preview", monkeypatch=monkeypatch
        )
    )

    assert native_capture == python_capture
    assert all(map(python_capture.__contains__, test_case.expected_fragments))


@pytest.mark.parametrize(
    "test_case",
    [
        MacroBridgeMemoTestCase(
            description="one global call text in three models",
            files=MACRO_BRIDGE_PROJECT_FILES,
            expected_python_executions=3,
            expected_native_executions=1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_repeated_macro_calls_when_rendering_natively_then_each_call_class_runs_once(
    test_case: MacroBridgeMemoTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir: Path = write_project(root=tmp_path / "project", files=test_case.files)
    executions: dict[str, int] = {}
    for engine in ("python", "native-preview"):
        log_path: Path = tmp_path / f"{engine}.log"
        monkeypatch.setenv(MACRO_CALL_LOG_ENV_VAR, str(log_path))
        _ = render_compile_inputs(project_dir=project_dir, engine=engine, monkeypatch=monkeypatch)
        executions[engine] = len(log_path.read_text(encoding="utf-8").splitlines())

    assert executions == {
        "python": test_case.expected_python_executions,
        "native-preview": test_case.expected_native_executions,
    }


@pytest.mark.parametrize(
    "test_case",
    [
        MacroBridgeFailureTestCase(
            description="macro raises in a later model",
            files={
                **_FAILURE_BASE_FILES,
                "models/b_second.sql": (
                    'MODEL (description "Second");\n\nSELECT @explode("amount") AS bogus\n'
                ),
            },
            expected_message_fragment="failed: cannot render amount",
        ),
        MacroBridgeFailureTestCase(
            description="unknown macro after a successful call",
            files={
                **_FAILURE_BASE_FILES,
                "models/b_second.sql": (
                    'MODEL (description "Second");\n\n'
                    'SELECT @cents("amount") AS a, @nope("amount") AS b\n'
                ),
            },
            expected_message_fragment="Unknown macro '@nope'",
        ),
        MacroBridgeFailureTestCase(
            description="macro returns a value that is not SQL",
            files={
                **_FAILURE_BASE_FILES,
                "models/b_second.sql": (
                    'MODEL (description "Second");\n\nSELECT @number("amount") AS b\n'
                ),
            },
            expected_message_fragment="must return a SQL string",
        ),
        MacroBridgeFailureTestCase(
            description="malformed call after a successful call",
            files={
                **_FAILURE_BASE_FILES,
                "models/b_second.sql": (
                    'MODEL (description "Second");\n\n'
                    'SELECT @cents("amount") AS a, @cents x("amount") AS b\n'
                ),
            },
            expected_message_fragment="expected opening parenthesis",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_failing_render_when_rendering_natively_then_raises_the_python_error(
    test_case: MacroBridgeFailureTestCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir: Path = write_project(root=tmp_path / "project", files=test_case.files)

    python_error: tuple[type[BaseException], str, type[object]] = render_error(
        project_dir=project_dir, engine="python", monkeypatch=monkeypatch
    )
    native_error: tuple[type[BaseException], str, type[object]] = render_error(
        project_dir=project_dir, engine="native-preview", monkeypatch=monkeypatch
    )

    assert native_error == python_error
    assert test_case.expected_message_fragment in python_error[1]


@pytest.mark.parametrize(
    "test_case",
    [
        MacroExpansionDifferentialTestCase(
            description="seeded fragments",
            seed=540,
            samples=3000,
            expected_minimum_successes=600,
            expected_mismatches=[],
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_random_macro_sql_when_expanding_through_bridge_then_matches_python(
    test_case: MacroExpansionDifferentialTestCase,
) -> None:
    rng: random.Random = random.Random(test_case.seed)
    texts: list[str] = [random_macro_sql(rng=rng) for _ in range(test_case.samples)]
    bridge: MacroBridge = MacroBridge(
        python_version=(sys.version_info[0], sys.version_info[1]),
        unicode_version=unicodedata.unidata_version,
    )

    python_outcomes: list[tuple[object, ...]] = [
        expansion_outcome(sql=sql, bridge=None) for sql in texts
    ]
    bridged_outcomes: list[tuple[object, ...]] = [
        expansion_outcome(sql=sql, bridge=bridge) for sql in texts
    ]

    assert (
        mismatches(
            inputs=list[object](texts),
            expected=list[object](python_outcomes),
            actual=list[object](bridged_outcomes),
        )
        == test_case.expected_mismatches
    )
    assert sum(len(outcome) == 5 for outcome in python_outcomes) >= (
        test_case.expected_minimum_successes
    )
    assert bridge.stats()[0] > 0


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
