from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from sqlbuild.compiler.compile.main.build_compile_inputs import build_compile_inputs
from sqlbuild.compiler.compile.models import CompileProjectInputs
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from tests.unit.src.sqlbuild.compiler.compile._test_types import (
    CursorStartCompileErrorTestCase,
    CursorStartCompileInputsTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        CursorStartCompileInputsTestCase(
            description="model cursor_start overrides path and project defaults",
            repo_files={
                "sqlbuild_project.yml": (
                    "name: demo\nadapter: duckdb\ndefaults:\n  cursor_start: 10\n"
                    "path_defaults:\n  models/events:\n    cursor_start: 20\n"
                ),
                "models/events/orders.sql": (
                    "MODEL (\nmaterialized: incremental\nincremental_strategy: delete_insert\n"
                    "cursor: id\ncursor_type: integer\ncursor_start: 30\n);\n\nSELECT 1 AS id"
                ),
            },
            expected_cursor_start=30,
        )
    ],
    ids=["model cursor_start overrides path and project defaults"],
)
def test_given_cursor_start_layers_when_building_compile_inputs_then_model_uses_model_precedence(
    test_case: CursorStartCompileInputsTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, test_case.repo_files)

    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=tmp_path)
    compile_inputs: CompileProjectInputs = build_compile_inputs(discovered_inputs)

    assert (
        test_case.expected_cursor_start
        == compile_inputs.model_inputs[0].config.values["cursor_start"]
    )


ERROR_TEST_CASES: list[CursorStartCompileErrorTestCase] = [
    CursorStartCompileErrorTestCase(
        description="cursor_start requires cursor",
        repo_files={
            "sqlbuild_project.yml": "name: demo\nadapter: duckdb\n",
            "models/orders.sql": (
                "MODEL (\nmaterialized: incremental\nincremental_strategy: merge\n"
                "cursor_type: integer\ncursor_start: 100\n);\n\nSELECT 1 AS id"
            ),
        },
        expected_error_fragment="cursor_start requires cursor",
    ),
    CursorStartCompileErrorTestCase(
        description="integer cursor_start rejects non whole number",
        repo_files={
            "sqlbuild_project.yml": "name: demo\nadapter: duckdb\n",
            "models/orders.sql": (
                "MODEL (\nmaterialized: incremental\nincremental_strategy: merge\ncursor: id\n"
                'cursor_type: integer\nunique_key: ["id"]\n'
                'cursor_start: "3.14"\n);\n\nSELECT 1 AS id'
            ),
        },
        expected_error_fragment="cursor_start value '3.14' is not a whole number",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    ERROR_TEST_CASES,
    ids=[case.description for case in ERROR_TEST_CASES],
)
def test_given_invalid_cursor_start_when_building_compile_inputs_then_raises_clear_error(
    test_case: CursorStartCompileErrorTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
) -> None:
    write_repo_files(tmp_path, test_case.repo_files)

    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(project_dir=tmp_path)

    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        build_compile_inputs(discovered_inputs)
