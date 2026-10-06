"""Unit-test selectors: split them from resource selectors or reject them where tests never run."""

from __future__ import annotations

from fnmatch import fnmatchcase

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.planner._helpers.graph.selectors import (
    parse_selector,
    selector_name_help,
    unit_test_selector_rejection,
)
from sqlbuild.compiler.planner.constants import (
    UNIT_TEST_SELECTOR_ERROR_CODE,
    UNKNOWN_SELECTOR_ERROR_CODE,
)
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.models import (
    ParsedSelector,
    PathSelector,
    SqlTestSelection,
    UnitTestSelectorNames,
    UnitTestSelectorSplit,
)
from sqlbuild.compiler.planner.types import SelectorKind


def split_discovered_unit_test_selectors(
    *,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
    discovered_inputs: DiscoveredProjectInputs,
    accepts_unit_tests: bool,
) -> UnitTestSelectorSplit:
    """Split unit-test selectors from resource selectors using discovered project names."""

    return split_unit_test_selectors(
        select=select,
        exclude=exclude,
        names=UnitTestSelectorNames(
            tests=_unit_test_names(discovered_inputs),
            resources=_resource_names(discovered_inputs),
        ),
        accepts_unit_tests=accepts_unit_tests,
    )


def split_unit_test_selectors(
    *,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
    names: UnitTestSelectorNames,
    accepts_unit_tests: bool,
) -> UnitTestSelectorSplit:
    """Move unit-test selectors out of resource selectors, or reject them for this command."""

    selected_tests, resource_select = _split_groups(
        groups=select, names=names, accepts_unit_tests=accepts_unit_tests
    )
    excluded_tests, resource_exclude = _split_groups(
        groups=exclude, names=names, accepts_unit_tests=accepts_unit_tests
    )
    return UnitTestSelectorSplit(
        select=resource_select,
        exclude=resource_exclude,
        sql_test_selection=SqlTestSelection(
            names=selected_tests,
            excluded_names=excluded_tests,
            models_selected=not select or bool(resource_select) or not selected_tests,
        ),
    )


def _split_groups(
    *, groups: tuple[str, ...], names: UnitTestSelectorNames, accepts_unit_tests: bool
) -> tuple[frozenset[str], tuple[str, ...]]:
    tests: set[str] = set()
    kept_groups: list[str] = []
    for group in groups:
        tokens: list[str] = group.split()
        kept_tokens: list[str] = []
        for token in tokens:
            matched, keep = _split_token(
                token=token, names=names, accepts_unit_tests=accepts_unit_tests
            )
            tests.update(matched)
            if keep:
                kept_tokens.append(token)
        if len(kept_tokens) == len(tokens):
            kept_groups.append(group)
        elif kept_tokens:
            kept_groups.append(" ".join(kept_tokens))
    return frozenset(tests), tuple(kept_groups)


def _split_token(
    *, token: str, names: UnitTestSelectorNames, accepts_unit_tests: bool
) -> tuple[frozenset[str], bool]:
    parts: list[str] = token.split(",")
    classified: list[tuple[frozenset[str], bool]] = [
        _classify(part=part, names=names, accepts_unit_tests=accepts_unit_tests) for part in parts
    ]
    selects_tests: bool = any(matched and not keep for matched, keep in classified)
    if len(parts) > 1 and selects_tests:
        for part in parts:
            parse_selector(part)
        raise PlannerInputError(
            f"selector '{token}' intersects a unit test with ','; unit tests can only be "
            "selected whole, by name",
            code=UNIT_TEST_SELECTOR_ERROR_CODE,
        )
    if len(parts) > 1:
        return frozenset(), True
    return classified[0]


def _classify(
    *, part: str, names: UnitTestSelectorNames, accepts_unit_tests: bool
) -> tuple[frozenset[str], bool]:
    """Return the unit tests one selector selects and whether it also selects resources."""

    try:
        parsed: ParsedSelector | PathSelector = parse_selector(part)
    except PlannerInputError:
        return frozenset(), True
    if isinstance(parsed, PathSelector) or parsed.kind not in {
        SelectorKind.NAME,
        SelectorKind.TEST,
    }:
        return frozenset(), True
    matched_tests: frozenset[str] = _matching(value=parsed.value, names=names.tests)
    selects_resources: bool = parsed.kind == SelectorKind.NAME and bool(
        _matching(value=parsed.value, names=names.resources)
    )
    if selects_resources:
        return frozenset(), True
    if not matched_tests:
        if parsed.kind == SelectorKind.TEST or accepts_unit_tests:
            _raise_unknown(parsed=parsed, names=names)
        return frozenset(), True
    if not accepts_unit_tests:
        raise unit_test_selector_rejection(selector=part)
    if parsed.upstream or parsed.downstream:
        raise PlannerInputError(
            f"selector '{part}' expands a unit test with '+'; unit tests have no lineage, so "
            "select them by name without '+'",
            code=UNIT_TEST_SELECTOR_ERROR_CODE,
        )
    return matched_tests, False


def _raise_unknown(*, parsed: ParsedSelector, names: UnitTestSelectorNames) -> None:
    label: str = "pattern" if _is_pattern(parsed.value) else "name"
    candidates: frozenset[str] = names.tests
    subject: str = "unit test"
    if parsed.kind == SelectorKind.NAME:
        candidates = names.tests | names.resources
        subject = "selector"
    raise PlannerInputError(
        f"unknown {subject} {label} '{parsed.value}'",
        code=UNKNOWN_SELECTOR_ERROR_CODE,
        help=selector_name_help(value=parsed.value, candidates=candidates),
    )


def _matching(*, value: str, names: frozenset[str]) -> frozenset[str]:
    if not _is_pattern(value):
        return frozenset({value}) & names
    return frozenset(name for name in names if fnmatchcase(name, value))


def _is_pattern(value: str) -> bool:
    return any(character in value for character in "*?[")


def _unit_test_names(discovered_inputs: DiscoveredProjectInputs) -> frozenset[str]:
    names: set[str] = set()
    for test_file in discovered_inputs.test_files:
        names.update(block.name or test_file.relative_path.stem for block in test_file.blocks)
    return frozenset(names)


def _resource_names(discovered_inputs: DiscoveredProjectInputs) -> frozenset[str]:
    names: set[str] = {model_file.file_path.stem for model_file in discovered_inputs.model_files}
    for schema_file in discovered_inputs.schema_files:
        names.update(entry.name for entry in schema_file.model_entries)
        names.update(entry.name for entry in schema_file.seed_entries)
    for source_file in discovered_inputs.source_files:
        names.update(entry.name for entry in source_file.source_entries)
    names.update(seed_file.file_path.stem for seed_file in discovered_inputs.seed_files)
    names.update(
        function_file.file_path.stem
        for function_file in (
            *discovered_inputs.sql_function_files,
            *discovered_inputs.python_function_files,
        )
    )
    names.update(
        node.name
        for node in (
            *discovered_inputs.loader_functions,
            *discovered_inputs.task_functions,
            *discovered_inputs.asset_functions,
            *discovered_inputs.check_functions,
        )
    )
    return frozenset(names)
