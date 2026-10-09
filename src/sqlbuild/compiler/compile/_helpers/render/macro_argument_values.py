"""Build macro call arguments from the value plan native parsing returns for their text."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import cast

import sqlbuild._native as _native
from sqlbuild.compiler.compile._helpers.explicit_references.macro_arguments import (
    typed_reference_value,
)
from sqlbuild.compiler.compile.constants import MACRO_ARGUMENT_ERROR_TAG
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import ParsedMacroArguments
from sqlbuild.compiler.frontier.main.report_native_answer import report_native_answer
from sqlbuild.compiler.frontier.types import NativeStage

type _ValueRow = tuple[object, ...]
type _BuildContext = tuple[Sequence[object], str]
_BUILDERS: dict[str, Callable[..., object]] = {
    "s": lambda *, row, context: row[1],
    "b": lambda *, row, context: row[1],
    "n": lambda *, row, context: None,
    "i": lambda *, row, context: int(cast(str, row[2]), cast(int, row[1])),
    "f": lambda *, row, context: float(cast(str, row[1])),
    "c": lambda *, row, context: context[0][cast(int, row[1])],
    "r": lambda *, row, context: typed_reference_value(
        function=cast(str, row[1]), name=cast(str, row[2])
    ),
    "l": lambda *, row, context: _items(row=row, context=context),
    "t": lambda *, row, context: tuple(_items(row=row, context=context)),
    "d": lambda *, row, context: _mapping(row=row, context=context),
    "-": lambda *, row, context: -_number(row=row, context=context),
    "+": lambda *, row, context: _number(row=row, context=context),
}


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
    if parsed[0] == MACRO_ARGUMENT_ERROR_TAG:
        _, detail, help_text, line, column = parsed
        raise CompileInputError(
            f"Macro arguments in '{file_path}' {detail} at line {line}, column {column} of {label}",
            help=cast(str, help_text),
        )
    _, positional, keywords, references = parsed
    report_native_answer(stage=NativeStage.MACRO_CALLS, kind="parsed_arguments")
    context: _BuildContext = (nested_values, f"'{file_path}' in {label}")
    return ParsedMacroArguments(
        args=tuple(_built(row=row, context=context) for row in cast(list[_ValueRow], positional)),
        kwargs={
            name: _built(row=row, context=context)
            for name, row in cast(list[tuple[str, _ValueRow]], keywords)
        },
        typed_references=tuple(
            typed_reference_value(function=function, name=name)
            for function, name in cast(list[tuple[str, str]], references)
        ),
    )


def _built(*, row: _ValueRow, context: _BuildContext) -> object:
    return _BUILDERS[cast(str, row[0])](row=row, context=context)


def _items(*, row: _ValueRow, context: _BuildContext) -> list[object]:
    return [_built(row=item, context=context) for item in cast(list[_ValueRow], row[1])]


def _mapping(*, row: _ValueRow, context: _BuildContext) -> dict[object, object]:
    return {
        _built(row=key, context=context): _built(row=value, context=context)
        for key, value in cast(list[tuple[_ValueRow, _ValueRow]], row[1])
    }


def _number(*, row: _ValueRow, context: _BuildContext) -> int | float:
    number: object = _built(row=cast(_ValueRow, row[1]), context=context)
    if not isinstance(number, int | float):
        raise CompileInputError(
            f"Macro arguments in {context[1]} use unary + or - on a value that is not a number",
            help="Apply the sign inside the macro, or pass a number literal",
        )
    return number
