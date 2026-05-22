"""Tests for sqb load selector resolution."""

from __future__ import annotations

import pytest

from sqlbuild.cli.commands.main.helpers.load_selection import select_load_entries
from sqlbuild.spec.models.source import SourceEntry
from tests.unit.src.sqlbuild.cli.commands.main.helpers.load_selection._test_types import (
    LoadSelectionTestCase,
)
from tests.unit.src.sqlbuild.cli.commands.main.helpers.load_selection.helpers import (
    build_load_selection_inputs,
)

LOAD_SELECTION_TEST_CASES: list[LoadSelectionTestCase] = [
    LoadSelectionTestCase(
        description="source selector wins over same-named intermediate loader",
        select=("raw_orders",),
        expected_entry_names=("raw_orders",),
        expected_loader_node_flags=(False,),
    ),
    LoadSelectionTestCase(
        description="leading plus includes upstream intermediate loader",
        select=("+raw_orders",),
        expected_entry_names=("fetch_orders", "raw_orders"),
        expected_loader_node_flags=(True, False),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    LOAD_SELECTION_TEST_CASES,
    ids=[case.description for case in LOAD_SELECTION_TEST_CASES],
)
def test_given_load_selector_when_selecting_then_returns_expected_source_entries(
    test_case: LoadSelectionTestCase,
) -> None:
    entries: tuple[SourceEntry, ...] = select_load_entries(
        discovered_inputs=build_load_selection_inputs(),
        select=test_case.select,
        exclude=(),
        environment_config=None,
    )

    assert tuple(entry.name for entry in entries) == test_case.expected_entry_names
    assert (
        tuple(entry.meta.get("sqlbuild_loader_node") is True for entry in entries)
        == test_case.expected_loader_node_flags
    )
