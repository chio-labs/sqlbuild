"""Process-wide transient terminal line coordination."""

from __future__ import annotations

from sqlbuild.presentation.classes.transient_line_coordinator import TransientLineCoordinator

_SHARED_COORDINATOR: TransientLineCoordinator = TransientLineCoordinator()


def shared_transient_line_coordinator() -> TransientLineCoordinator:
    """Return the coordinator shared by every terminal writer in this process."""

    return _SHARED_COORDINATOR
