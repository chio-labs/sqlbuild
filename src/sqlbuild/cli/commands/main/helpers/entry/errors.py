"""CLI entrypoint error rendering helpers."""

from __future__ import annotations

import argparse
import sys
from typing import NoReturn


class SqlbuildArgumentParser(argparse.ArgumentParser):
    """Argument parser that renders parser failures with a stable code."""

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: error[C900]: {message}\n")


def format_expected_error(error: Exception, *, fallback_code: str) -> str:
    code: str = str(getattr(error, "code", fallback_code))
    message: str = str(getattr(error, "message", str(error)))
    rendered: str = f"error[{code}]: {message}"
    help_text: str | None = getattr(error, "help", None)
    if help_text is not None:
        rendered = f"{rendered}\n  = help: {help_text}"
    return rendered
