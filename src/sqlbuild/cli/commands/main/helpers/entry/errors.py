"""CLI entrypoint error rendering helpers."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from typing import NoReturn

from sqlbuild.shared.helpers.cli_style import CliStyle
from sqlbuild.shared.main.coded_error_text import format_coded_error


class SqlbuildArgumentParser(argparse.ArgumentParser):
    """Argument parser that renders parser failures with a stable code."""

    use_color: bool = False

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        style: CliStyle = CliStyle(use_color=self.use_color)
        prefix: str = style.error_strong("error[C900]:")
        self.exit(2, f"{self.prog}: {prefix} {message}\n\n")


def build_argument_parser_class(*, use_color: bool) -> type[SqlbuildArgumentParser]:
    class ColorAwareSqlbuildArgumentParser(SqlbuildArgumentParser):
        pass

    ColorAwareSqlbuildArgumentParser.use_color = use_color

    return ColorAwareSqlbuildArgumentParser


def format_expected_error(error: Exception, *, fallback_code: str, use_color: bool) -> str:
    code: str = str(getattr(error, "code", fallback_code))
    message: str = str(getattr(error, "message", str(error)))
    help_text: str | None = getattr(error, "help", None)
    return (
        format_coded_error(code=code, message=message, help=help_text, use_color=use_color) + "\n"
    )


def cli_error_use_color(
    argv: Sequence[str] | None,
    *,
    supports_color: Callable[[], bool],
) -> bool:
    raw_args: Sequence[str] = sys.argv[1:] if argv is None else argv
    return "--no-color" not in raw_args and supports_color()
