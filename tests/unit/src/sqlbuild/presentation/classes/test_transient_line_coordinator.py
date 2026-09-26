from __future__ import annotations

import pytest

from sqlbuild.presentation.classes.transient_line_coordinator import TransientLineCoordinator
from tests.unit.src.sqlbuild.presentation.classes._test_types import (
    TransientLineCoordinatorTestCase,
)
from tests.unit.src.sqlbuild.presentation.classes.helpers import (
    RecordingSpinnerOwner,
    RecordingStream,
)


@pytest.mark.parametrize(
    "test_case",
    (
        TransientLineCoordinatorTestCase(
            description="persistent line on the live terminal clears then redraws the spinner",
            persistent_stream_is_tty=True,
            expected_events=("clear", "write:Warehouse connected\n", "redraw"),
        ),
        TransientLineCoordinatorTestCase(
            description="redirected output does not disturb the terminal spinner",
            persistent_stream_is_tty=False,
            expected_events=("write:Warehouse connected\n",),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_live_spinner_when_writing_persistent_line_then_line_never_joins_spinner(
    test_case: TransientLineCoordinatorTestCase,
) -> None:
    events: list[str] = []
    coordinator: TransientLineCoordinator = TransientLineCoordinator()
    owner: RecordingSpinnerOwner = RecordingSpinnerOwner(events=events)
    coordinator.claim(stream=RecordingStream(events=[], tty=True), owner=owner)

    coordinator.write_persistent(
        stream=RecordingStream(events=events, tty=test_case.persistent_stream_is_tty),
        text="Warehouse connected\n",
    )

    assert tuple(events) == test_case.expected_events


@pytest.mark.parametrize(
    "test_case",
    (
        TransientLineCoordinatorTestCase(
            description="released spinner is neither cleared nor redrawn",
            persistent_stream_is_tty=True,
            expected_events=("write:Warehouse connected\n",),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_released_spinner_when_writing_persistent_line_then_writes_directly(
    test_case: TransientLineCoordinatorTestCase,
) -> None:
    events: list[str] = []
    coordinator: TransientLineCoordinator = TransientLineCoordinator()
    owner: RecordingSpinnerOwner = RecordingSpinnerOwner(events=events)
    coordinator.claim(stream=RecordingStream(events=[], tty=True), owner=owner)
    coordinator.release(owner=owner)

    coordinator.write_persistent(
        stream=RecordingStream(events=events, tty=test_case.persistent_stream_is_tty),
        text="Warehouse connected\n",
    )

    assert tuple(events) == test_case.expected_events


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
