"""Public validation that a command which never runs unit tests selects none."""

from __future__ import annotations

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.planner.main.selection._split_unit_test_selectors import (
    split_project_unit_test_selectors,
)
from sqlbuild.compiler.planner.models import UnitTestSelectorSplit


def reject_unit_test_selectors(
    *,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
    discovered_inputs: DiscoveredProjectInputs,
) -> UnitTestSelectorSplit:
    """Raise when a selector names a unit test; return the unchanged resource selectors."""

    return split_project_unit_test_selectors(
        select=select,
        exclude=exclude,
        discovered_inputs=discovered_inputs,
        accepts_unit_tests=False,
    )
