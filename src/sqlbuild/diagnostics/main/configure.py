"""Diagnostics logging configuration entrypoint."""

from __future__ import annotations

import logging
from pathlib import Path

from sqlbuild.diagnostics._helpers.logging import (
    get_diagnostics_logger,
)
from sqlbuild.diagnostics.classes.diagnostics_console_formatter import DiagnosticsConsoleFormatter
from sqlbuild.diagnostics.classes.diagnostics_file_formatter import DiagnosticsFileFormatter
from sqlbuild.diagnostics.classes.dynamic_stderr_handler import DynamicStderrHandler


def configure_diagnostics(*, target_dir: Path, debug: bool, use_color: bool = False) -> None:
    """Configure SQLBuild diagnostics logging for one CLI invocation."""

    _LOG_FILE_NAME: str = "sqlbuild.log"
    target_dir.mkdir(parents=True, exist_ok=True)
    logger: logging.Logger = get_diagnostics_logger()
    logger.setLevel(logging.DEBUG)
    logger.propagate = True

    handler: logging.Handler
    for handler in tuple(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    file_handler: logging.FileHandler = logging.FileHandler(
        target_dir / _LOG_FILE_NAME,
        mode="w",
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(DiagnosticsFileFormatter())
    logger.addHandler(file_handler)

    if debug:
        console_handler: logging.StreamHandler = DynamicStderrHandler()
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(DiagnosticsConsoleFormatter(use_color=use_color))
        logger.addHandler(console_handler)
