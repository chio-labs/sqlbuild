"""CLI entrypoint error rendering helpers."""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence

from sqlbuild.cli.commands.classes.sqlbuild_argument_parser import SqlbuildArgumentParser
from sqlbuild.cli.commands.helpers.entry.constants import NO_COLOR_OPTION
from sqlbuild.presentation.main.coded_error_text import format_coded_error


def build_argument_parser_class(*, use_color: bool) -> type[SqlbuildArgumentParser]:
    class ColorAwareSqlbuildArgumentParser(SqlbuildArgumentParser):
        pass

    ColorAwareSqlbuildArgumentParser.use_color = use_color

    return ColorAwareSqlbuildArgumentParser


def format_expected_error(*, error: Exception, fallback_code: str, use_color: bool) -> str:
    code: str = str(getattr(error, "code", fallback_code))
    message: str = str(getattr(error, "message", str(error)))
    help_text: str | None = getattr(error, "help", None)
    return (
        format_coded_error(code=code, message=message, help=help_text, use_color=use_color) + "\n"
    )


def cli_error_use_color(
    *,
    argv: Sequence[str] | None,
    supports_color: Callable[[], bool],
) -> bool:
    raw_args: Sequence[str] = sys.argv[1:] if argv is None else argv
    return NO_COLOR_OPTION not in raw_args and supports_color()
