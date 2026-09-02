"""Execution-event side-channel detection entrypoint."""

from __future__ import annotations

import os
from pathlib import Path

from sqlbuild.cli.output.constants import INTEGRATION_RESULT_PATH_ENV


def execution_event_output_active(*, path: Path | None = None) -> bool:
    """Return whether this command emits the integration-result side-channel."""

    return path is not None or os.environ.get(INTEGRATION_RESULT_PATH_ENV) is not None
