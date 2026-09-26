"""Public shared transient line coordinator entry."""

from __future__ import annotations

from sqlbuild.presentation._helpers.transient_line import (
    shared_transient_line_coordinator as _shared_transient_line_coordinator,
)
from sqlbuild.presentation.classes.transient_line_coordinator import TransientLineCoordinator


def shared_transient_line_coordinator() -> TransientLineCoordinator:
    """Return the coordinator shared by every terminal writer in this process."""

    return _shared_transient_line_coordinator()
