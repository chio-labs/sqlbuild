"""Tests for sqb load selector resolution."""

from __future__ import annotations

import pytest

from sqlbuild.cli.commands.main.helpers.load.selection import (
    select_load_entries,
    select_load_reference_entries,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.spec.models.source import SourceEntry
from tests.unit.src.sqlbuild.cli.commands.main.helpers.load_selection._test_types import (
    LoadReferenceSelectionTestCase,
    LoadSelectionTestCase,
)
from tests.unit.src.sqlbuild.cli.commands.main.helpers.load_selection.helpers import (
    build_integration_load_selection_inputs,
    build_load_selection_inputs,
)

LOAD_SELECTION_TEST_CASES: list[LoadSelectionTestCase] = [
    LoadSelectionTestCase(
        description="source selector selects terminal source load only",
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
        target_config=None,
    )

    assert tuple(entry.name for entry in entries) == test_case.expected_entry_names
    assert (
        tuple(entry.meta.get("sqlbuild_loader_node") is True for entry in entries)
        == test_case.expected_loader_node_flags
    )


@pytest.mark.parametrize(
    "test_case",
    [
        LoadReferenceSelectionTestCase(
            description="integration terminal loader is selected, not reference-only",
            select=("raw_orders",),
            expected_entry_names=(),
        )
    ],
    ids=["integration terminal loader is selected, not reference-only"],
)
def test_given_integration_loader_selected_when_selecting_references_then_returns_no_terminal_ref(
    test_case: LoadReferenceSelectionTestCase,
) -> None:
    discovered_inputs: DiscoveredProjectInputs = build_integration_load_selection_inputs()
    selected_entries: tuple[SourceEntry, ...] = select_load_entries(
        discovered_inputs=discovered_inputs,
        select=test_case.select,
        exclude=(),
        target_config=None,
    )

    reference_entries: tuple[SourceEntry, ...] = select_load_reference_entries(
        discovered_inputs=discovered_inputs,
        selected_sources=selected_entries,
        target_config=None,
    )

    assert tuple(entry.name for entry in reference_entries) == test_case.expected_entry_names
