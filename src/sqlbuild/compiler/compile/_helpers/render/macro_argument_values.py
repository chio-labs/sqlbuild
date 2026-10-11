"""Build macro call arguments from the value plan native parsing returns for their text."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import cast

import sqlbuild._native as _native
from sqlbuild.compiler.compile._helpers.explicit_references.macro_arguments import (
    typed_reference_value,
)
from sqlbuild.compiler.compile.constants import (
    MACRO_ARGUMENT_ERROR_TAG,
    MACRO_ARGUMENT_NESTED_CALL_TAG,
)
from sqlbuild.compiler.compile.exceptions import MacroArgumentError
from sqlbuild.compiler.compile.models import ParsedMacroArguments

type _ValueRow = tuple[object, ...]
type _BuildContext = tuple[Sequence[object], Callable[..., MacroArgumentError]]
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
    "-": lambda *, row, context: -_number(row=row, context=context, sign="-"),
    "+": lambda *, row, context: _number(row=row, context=context, sign="+"),
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

    def argument_error(*, offset: int, detail: str, help_text: str) -> MacroArgumentError:
        line: int = args_source.count("\n", 0, offset) + 1
        column: int = offset - (args_source.rfind("\n", 0, offset) + 1) + 1
        return MacroArgumentError(
            detail=detail,
            help=help_text,
            macro_name=macro_name,
            file_path=file_path,
            offset=offset,
            relative_position=(line, column),
        )

    if parsed[0] == MACRO_ARGUMENT_ERROR_TAG:
        _, detail, help_text, line, column = parsed
        line_start: int = sum(
            len(text) + 1 for text in args_source.split("\n")[: cast(int, line) - 1]
        )
        raise argument_error(
            offset=line_start + cast(int, column) - 1,
            detail=cast(str, detail),
            help_text=cast(str, help_text),
        )
    _, positional, keywords, references = parsed

    def unary_error(*, call: int, sign: str) -> MacroArgumentError:
        value: object = nested_values[call]
        return argument_error(
            offset=nested[call][0],
            detail=(
                f"apply unary {sign} to the value of a nested macro call, which is a "
                f"{type(value).__name__} and not a number"
            ),
            help_text="Return a number from the nested macro, or apply the sign inside the macro",
        )

    context: _BuildContext = (nested_values, unary_error)
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


def _number(*, row: _ValueRow, context: _BuildContext, sign: str) -> int | float:
    operand: _ValueRow = cast(_ValueRow, row[1])
    number: object = _built(row=operand, context=context)
    if not isinstance(number, int | float):
        raise context[1](call=_nested_call(operand), sign=sign)
    return number


def _nested_call(row: _ValueRow) -> int:
    """The nested call index under unary signs; only a nested call yields a non-number here."""

    while row[0] != MACRO_ARGUMENT_NESTED_CALL_TAG:
        row = cast(_ValueRow, row[1])
    return cast(int, row[1])
