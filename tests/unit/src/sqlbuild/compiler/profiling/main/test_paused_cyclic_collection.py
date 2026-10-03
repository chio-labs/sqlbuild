from __future__ import annotations

import gc
from collections.abc import Callable

import pytest

from sqlbuild.compiler.profiling.main.paused_cyclic_collection import paused_cyclic_collection
from tests.unit.src.sqlbuild.compiler.profiling.main._test_types import (
    PausedCyclicCollectionTestCase,
)

_SET_COLLECTION: dict[bool, Callable[[], None]] = {True: gc.enable, False: gc.disable}


@pytest.mark.parametrize(
    "test_case",
    (
        PausedCyclicCollectionTestCase(
            description="enabled_collector_resumes_only_after_outer_pause",
            enabled_before=True,
            expected_inside_inner=False,
            expected_after_inner=False,
            expected_after_outer=True,
        ),
        PausedCyclicCollectionTestCase(
            description="disabled_collector_stays_disabled",
            enabled_before=False,
            expected_inside_inner=False,
            expected_after_inner=False,
            expected_after_outer=False,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_nested_pauses_when_exiting_then_prior_collector_state_is_restored(
    test_case: PausedCyclicCollectionTestCase,
) -> None:
    was_enabled: bool = gc.isenabled()
    _SET_COLLECTION[test_case.enabled_before]()
    try:
        with paused_cyclic_collection():
            with paused_cyclic_collection():
                inside_inner: bool = gc.isenabled()
            after_inner: bool = gc.isenabled()
        after_outer: bool = gc.isenabled()
    finally:
        _SET_COLLECTION[was_enabled]()

    assert (inside_inner, after_inner, after_outer) == (
        test_case.expected_inside_inner,
        test_case.expected_after_inner,
        test_case.expected_after_outer,
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
