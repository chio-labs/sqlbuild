"""Build macro call arguments from the value plan native parsing returns for their text."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import cast

import sqlbuild._native as _native
from sqlbuild.compiler.compile._helpers.explicit_references.macro_arguments import (
    typed_reference_value,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import ParsedMacroArguments
from sqlbuild.compiler.frontier.main.report_native_answer import report_native_answer
from sqlbuild.compiler.frontier.types import NativeStage

type _ValueRow = tuple[object, ...]


def parse_macro_call_arguments(
    *,
    args_source: str,
    nested: tuple[tuple[int, int], ...],
    nested_values: Sequence[object],
    macro_name: str,
    file_path: Path,
) -> ParsedMacroArguments:
    """Parse `args_source` natively; nested calls at `nested` take their `nested_values`."""

    parsed: tuple[object, ...] = _native.parse_macro_arguments(args_source, list(nested))
    label: str = f"the '@{macro_name}' arguments"
    if parsed[0] == "error":
        _, detail, help_text, line, column = parsed
        raise CompileInputError(
            f"Macro arguments in '{file_path}' {detail} at line {line}, column {column} of {label}",
            help=cast(str, help_text),
        )
    _, positional, keywords, references = parsed
    report_native_answer(stage=NativeStage.MACRO_CALLS, kind="parsed_arguments")
    context: tuple[Sequence[object], str] = (nested_values, f"'{file_path}' in {label}")
    return ParsedMacroArguments(
        args=tuple(_built(row, context) for row in cast(list[_ValueRow], positional)),
        kwargs={
            name: _built(row, context) for name, row in cast(list[tuple[str, _ValueRow]], keywords)
        },
        typed_references=tuple(
            typed_reference_value(function=function, name=name)
            for function, name in cast(list[tuple[str, str]], references)
        ),
    )


def _built(row: _ValueRow, context: tuple[Sequence[object], str]) -> object:
    tag: object = row[0]
    if tag in ("s", "b"):
        return row[1]
    if tag == "i":
        return int(cast(str, row[2]), cast(int, row[1]))
    if tag == "f":
        return float(cast(str, row[1]))
    if tag == "c":
        return context[0][cast(int, row[1])]
    if tag == "r":
        return typed_reference_value(function=cast(str, row[1]), name=cast(str, row[2]))
    if tag == "l":
        return [_built(item, context) for item in cast(list[_ValueRow], row[1])]
    if tag == "t":
        return tuple(_built(item, context) for item in cast(list[_ValueRow], row[1]))
    if tag == "d":
        return {
            _built(key, context): _built(value, context)
            for key, value in cast(list[tuple[_ValueRow, _ValueRow]], row[1])
        }
    if tag in ("-", "+"):
        number: object = _built(cast(_ValueRow, row[1]), context)
        if not isinstance(number, int | float):
            raise CompileInputError(
                f"Macro arguments in {context[1]} use unary + or - on a value that is not a number",
                help="Apply the sign inside the macro, or pass a number literal",
            )
        return -number if tag == "-" else number
    return None
