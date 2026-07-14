from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.cli.commands._helpers.scenario.selection import select_scenarios
from sqlbuild.cli.exceptions import CliUserError
from sqlbuild.compiler.compile.models.core import CompiledProject, CompiledSqlScenario
from tests.unit.src.sqlbuild.cli.commands._helpers.scenario._test_types import (
    SelectScenariosErrorTestCase,
    SelectScenariosTestCase,
)
from tests.unit.src.sqlbuild.cli.commands._helpers.scenario.helpers import (
    build_project_with_scenarios,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SelectScenariosTestCase(
            description="excludes scenarios from explicit selection",
            selectors=("tests/scenarios",),
            exclude=("orders_refund",),
            expected_scenario_names=("orders_paid",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_scenario_selectors_when_excluding_then_returns_remaining_scenarios(
    test_case: SelectScenariosTestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = tmp_path
    project: CompiledProject = build_project_with_scenarios(project_dir)

    selected: tuple[CompiledSqlScenario, ...] = select_scenarios(
        project=project,
        selectors=test_case.selectors,
        exclude=test_case.exclude,
        project_dir=project_dir,
    )

    assert tuple(scenario.name for scenario in selected) == test_case.expected_scenario_names


@pytest.mark.parametrize(
    "test_case",
    [
        SelectScenariosErrorTestCase(
            description="rejects upstream graph selector",
            selectors=("+orders_paid",),
            exclude=(),
            expected_error_fragment="uses graph operators, which are not supported",
            expected_error_code="C457",
        ),
        SelectScenariosErrorTestCase(
            description="rejects path graph selector",
            selectors=("orders_paid~orders_refund",),
            exclude=(),
            expected_error_fragment="uses graph operators, which are not supported",
            expected_error_code="C457",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_graph_scenario_selector_when_selecting_then_raises_clear_error(
    test_case: SelectScenariosErrorTestCase,
    tmp_path: Path,
) -> None:
    with pytest.raises(CliUserError) as exc_info:
        select_scenarios(
            project=build_project_with_scenarios(tmp_path),
            selectors=test_case.selectors,
            exclude=test_case.exclude,
            project_dir=tmp_path,
        )

    assert test_case.expected_error_fragment in str(exc_info.value)
    assert exc_info.value.code == test_case.expected_error_code
