"""Compiler-internal unit-test selector split entrypoint."""

from __future__ import annotations

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.planner._helpers.selection.unit_test_selectors import (
    split_discovered_unit_test_selectors,
)
from sqlbuild.compiler.planner.models import UnitTestSelectorSplit


def split_project_unit_test_selectors(
    *,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
    discovered_inputs: DiscoveredProjectInputs,
    accepts_unit_tests: bool,
) -> UnitTestSelectorSplit:
    """Move unit-test selectors out of resource selectors, or reject them for this command."""

    return split_discovered_unit_test_selectors(
        select=select,
        exclude=exclude,
        discovered_inputs=discovered_inputs,
        accepts_unit_tests=accepts_unit_tests,
    )
