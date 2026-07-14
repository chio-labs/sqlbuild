"""Scenario selector helpers shared by scenario CLI commands."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.cli.commands._helpers.scenario.constants import (
    GRAPH_SELECTOR_EXPANSION_MARKER,
    GRAPH_SELECTOR_PATH_MARKER,
    SCENARIO_CLI_NONE_DISCOVERED,
    SCENARIO_CLI_UNKNOWN_SELECTOR,
    SCENARIO_CLI_UNSUPPORTED_GRAPH_SELECTOR,
    SQL_FILE_SUFFIX,
)
from sqlbuild.cli.exceptions import CliUserError
from sqlbuild.compiler.compile.models.core import (
    CompiledProject,
    CompiledSqlScenario,
)


def select_scenarios(
    *,
    project: CompiledProject,
    selectors: tuple[str, ...],
    exclude: tuple[str, ...] = (),
    project_dir: Path,
) -> tuple[CompiledSqlScenario, ...]:
    """Resolve scenario names, files, and folder selectors into scenarios."""

    if not selectors:
        if not project.sql_scenarios:
            raise CliUserError(
                "No SQL scenarios were discovered under tests/scenarios",
                code=SCENARIO_CLI_NONE_DISCOVERED,
            )
        selected_scenarios: tuple[CompiledSqlScenario, ...] = project.sql_scenarios
    else:
        selected: list[CompiledSqlScenario] = []
        selected_names: set[str] = set()
        selector: str
        for selector in selectors:
            matches: tuple[CompiledSqlScenario, ...] = _select_scenarios_for_selector(
                project=project,
                selector=selector,
                project_dir=project_dir,
            )
            scenario: CompiledSqlScenario
            for scenario in matches:
                if scenario.name in selected_names:
                    continue
                selected.append(scenario)
                selected_names.add(scenario.name)
        selected_scenarios = tuple(selected)

    if not exclude:
        return selected_scenarios

    excluded_names: set[str] = set()
    exclude_selector: str
    for exclude_selector in exclude:
        excluded_names.update(
            scenario.name
            for scenario in _select_scenarios_for_selector(
                project=project,
                selector=exclude_selector,
                project_dir=project_dir,
            )
        )
    return tuple(scenario for scenario in selected_scenarios if scenario.name not in excluded_names)


def _select_scenarios_for_selector(
    *, project: CompiledProject, selector: str, project_dir: Path
) -> tuple[CompiledSqlScenario, ...]:
    _validate_scenario_selector(selector)
    selector_path: Path = Path(selector)
    matches: list[CompiledSqlScenario] = []
    scenario: CompiledSqlScenario
    for scenario in project.sql_scenarios:
        if scenario.name == selector:
            matches.append(scenario)
            continue
        scenario_path: Path = scenario.scenario_file.file_path
        scenario_relative_path: Path = scenario.scenario_file.relative_path
        scenario_root_relative_path: Path = _scenario_root_relative_path(scenario_relative_path)
        if selector_path.suffix == SQL_FILE_SUFFIX and _scenario_file_matches_selector(
            selector_path=selector_path,
            project_dir=project_dir,
            scenario_path=scenario_path,
            scenario_relative_path=scenario_relative_path,
            scenario_root_relative_path=scenario_root_relative_path,
        ):
            matches.append(scenario)
            continue
        if selector_path.suffix != SQL_FILE_SUFFIX and _scenario_path_is_under_selector(
            selector_path=selector_path,
            project_dir=project_dir,
            scenario_path=scenario_path,
            scenario_relative_path=scenario_relative_path,
            scenario_root_relative_path=scenario_root_relative_path,
        ):
            matches.append(scenario)
    if matches:
        return tuple(matches)
    raise CliUserError(
        f"Unknown scenario selector '{selector}'",
        code=SCENARIO_CLI_UNKNOWN_SELECTOR,
    )


def _validate_scenario_selector(selector: str) -> None:
    if (
        selector.startswith(GRAPH_SELECTOR_EXPANSION_MARKER)
        or selector.endswith(GRAPH_SELECTOR_EXPANSION_MARKER)
        or GRAPH_SELECTOR_PATH_MARKER in selector
    ):
        raise CliUserError(
            f"Scenario selector '{selector}' uses graph operators, which are not supported",
            code=SCENARIO_CLI_UNSUPPORTED_GRAPH_SELECTOR,
            help=(
                "Use scenario names, scenario file paths, folders, --select-file, and --exclude. "
                "Graph expansion operators such as '+model', 'model+', and 'a~b' are only "
                "supported by graph resource commands."
            ),
        )


def _scenario_file_matches_selector(
    *,
    selector_path: Path,
    project_dir: Path,
    scenario_path: Path,
    scenario_relative_path: Path,
    scenario_root_relative_path: Path,
) -> bool:
    return selector_path in (
        scenario_path,
        project_dir / selector_path,
        scenario_relative_path,
        scenario_root_relative_path,
    )


def _scenario_path_is_under_selector(
    *,
    selector_path: Path,
    project_dir: Path,
    scenario_path: Path,
    scenario_relative_path: Path,
    scenario_root_relative_path: Path,
) -> bool:
    selector_candidates: tuple[Path, ...] = (selector_path, project_dir / selector_path)
    candidate: Path
    for candidate in selector_candidates:
        if _path_is_under(path=scenario_path, prefix=candidate):
            return True
    return _path_is_under(path=scenario_relative_path, prefix=selector_path) or _path_is_under(
        path=scenario_root_relative_path,
        prefix=selector_path,
    )


def _path_is_under(*, path: Path, prefix: Path) -> bool:
    return path == prefix or prefix in path.parents


def _scenario_root_relative_path(relative_path: Path) -> Path:
    scenario_root: Path = Path("tests") / "scenarios"
    try:
        return relative_path.relative_to(scenario_root)
    except ValueError:
        return relative_path
