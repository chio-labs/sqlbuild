"""Public split of unit-test selectors from resource selectors for one command."""

from __future__ import annotations

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.planner.main.selection._split_unit_test_selectors import (
    split_project_unit_test_selectors,
)
from sqlbuild.compiler.planner.models import UnitTestSelectorSplit


def split_unit_test_selectors(
    *,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
    discovered_inputs: DiscoveredProjectInputs,
) -> UnitTestSelectorSplit:
    """Split unit-test selectors from resource selectors for a command that runs unit tests."""

    return split_project_unit_test_selectors(
        select=select,
        exclude=exclude,
        discovered_inputs=discovered_inputs,
        accepts_unit_tests=True,
    )
