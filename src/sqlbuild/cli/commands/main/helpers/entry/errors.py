"""CLI entrypoint error rendering helpers."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from typing import NoReturn

from sqlbuild.shared.helpers.coded_errors import format_coded_error
from sqlbuild.shared.helpers.colors import red_bold


class SqlbuildArgumentParser(argparse.ArgumentParser):
    """Argument parser that renders parser failures with a stable code."""

    use_color: bool = False

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        prefix: str = _style("error[C900]:", red_bold, use_color=self.use_color)
        self.exit(2, f"{self.prog}: {prefix} {message}\n")


def build_argument_parser_class(*, use_color: bool) -> type[SqlbuildArgumentParser]:
    class ColorAwareSqlbuildArgumentParser(SqlbuildArgumentParser):
        pass

    ColorAwareSqlbuildArgumentParser.use_color = use_color

    return ColorAwareSqlbuildArgumentParser


def format_expected_error(error: Exception, *, fallback_code: str, use_color: bool) -> str:
    code: str = str(getattr(error, "code", fallback_code))
    message: str = str(getattr(error, "message", str(error)))
    help_text: str | None = getattr(error, "help", None)
    return format_coded_error(code=code, message=message, help=help_text, use_color=use_color)


def cli_error_use_color(
    argv: Sequence[str] | None,
    *,
    supports_color: Callable[[], bool],
) -> bool:
    raw_args: Sequence[str] = sys.argv[1:] if argv is None else argv
    return "--no-color" not in raw_args and supports_color()


def _style(text: str, styler: Callable[[str], str], *, use_color: bool) -> str:
    if not use_color:
        return text
    return styler(text)
