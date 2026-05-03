"""Diagnostics logging configuration entrypoint."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from sqlbuild.diagnostics.shared.constants import (
    LOG_FILE_NAME,
)
from sqlbuild.diagnostics.shared.helpers.logging import (
    DiagnosticsConsoleFormatter,
    DiagnosticsFileFormatter,
)
from sqlbuild.shared.helpers.diagnostics_logging import (
    get_diagnostics_logger,
)


def configure_diagnostics(*, target_dir: Path, debug: bool, use_color: bool = False) -> None:
    """Configure SQLBuild diagnostics logging for one CLI invocation."""

    target_dir.mkdir(parents=True, exist_ok=True)
    logger: logging.Logger = get_diagnostics_logger()
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    handler: logging.Handler
    for handler in tuple(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    file_handler: logging.FileHandler = logging.FileHandler(
        target_dir / LOG_FILE_NAME,
        mode="w",
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(DiagnosticsFileFormatter())
    logger.addHandler(file_handler)

    if debug:
        console_handler: logging.StreamHandler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(DiagnosticsConsoleFormatter(use_color=use_color))
        logger.addHandler(console_handler)
