"""Rendering for reusable SQL resource arguments."""

from __future__ import annotations

from sqlbuild.compiler.compile.constants import (
    SQL_ARGUMENT_QUOTED_PARAMETER_PATTERN,
    SQL_ARGUMENT_RAW_PARAMETER_PATTERN,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError


def render_parameterized_sql(
    *,
    sql: str,
    arguments: dict[str, object],
    owner_label: str,
    definition_label: str,
    reject_unused: bool = False,
) -> str:
    """Render raw and quoted arguments into reusable SQL text."""

    referenced_argument_names: set[str] = set()
    for pattern in (
        SQL_ARGUMENT_QUOTED_PARAMETER_PATTERN,
        SQL_ARGUMENT_RAW_PARAMETER_PATTERN,
    ):
        referenced_argument_names.update(match.group("name") for match in pattern.finditer(sql))
    referenced_arguments: frozenset[str] = frozenset(referenced_argument_names)
    if reject_unused:
        unused_arguments: tuple[str, ...] = tuple(sorted(arguments.keys() - referenced_arguments))
        if unused_arguments:
            raise CompileInputError(
                f"{owner_label} passes unknown argument(s) to {definition_label}: "
                f"{', '.join(unused_arguments)}"
            )

    rendered_sql: str = SQL_ARGUMENT_QUOTED_PARAMETER_PATTERN.sub(
        lambda match: _render_argument(
            argument_name=match.group("name"),
            arguments=arguments,
            owner_label=owner_label,
            definition_label=definition_label,
            quoted=True,
        ),
        sql,
    )
    return SQL_ARGUMENT_RAW_PARAMETER_PATTERN.sub(
        lambda match: _render_argument(
            argument_name=match.group("name"),
            arguments=arguments,
            owner_label=owner_label,
            definition_label=definition_label,
            quoted=False,
        ),
        rendered_sql,
    )


def _render_argument(
    *,
    argument_name: str,
    arguments: dict[str, object],
    owner_label: str,
    definition_label: str,
    quoted: bool,
) -> str:
    if argument_name not in arguments:
        raise CompileInputError(
            f"{owner_label} is missing argument '{argument_name}' for {definition_label}"
        )
    return render_sql_argument_value(
        argument_value=arguments[argument_name],
        owner_label=owner_label,
        definition_label=definition_label,
        argument_name=argument_name,
        quoted=quoted,
    )


def render_sql_argument_value(
    *,
    argument_value: object,
    owner_label: str,
    definition_label: str,
    argument_name: str,
    quoted: bool,
) -> str:
    """Render one argument value using raw or SQL-literal semantics."""

    if isinstance(argument_value, list | tuple):
        return ", ".join(
            render_sql_argument_value(
                argument_value=item,
                owner_label=owner_label,
                definition_label=definition_label,
                argument_name=argument_name,
                quoted=quoted,
            )
            for item in argument_value
        )
    if isinstance(argument_value, bool):
        return "TRUE" if argument_value else "FALSE"
    if argument_value is None:
        return "NULL"
    if isinstance(argument_value, int | float):
        return str(argument_value)
    if isinstance(argument_value, str):
        if quoted:
            return f"'{argument_value.replace(chr(39), chr(39) * 2)}'"
        return argument_value
    raise CompileInputError(
        f"{owner_label} {definition_label} argument '{argument_name}' uses an unsupported value"
    )
