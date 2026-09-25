"""Names and types registered with native validation from project declarations."""

from sqlbuild.compiler.compile.models import CompiledFunction, CompileSqlFunctionInput


def known_function_names(
    functions: tuple[CompiledFunction, ...] | tuple[CompileSqlFunctionInput, ...],
) -> tuple[str, ...]:
    """Register authored names and the analysis-only scalar/table function names."""
    names: set[str] = set()
    for function in functions:
        names.update(
            (
                function.name,
                f"__sqlbuild_udf_{function.name}",
                f"__sqlbuild_table_function_{function.name}",
            )
        )
    return tuple(sorted(names))


def known_declared_types(
    *,
    functions: tuple[CompiledFunction, ...] | tuple[CompileSqlFunctionInput, ...],
    column_types: dict[str, dict[str, str]],
) -> tuple[str, ...]:
    """Register types named by relation contracts and scalar/table function signatures."""
    types: set[str] = set()
    for columns in column_types.values():
        types.update(columns.values())
    for function in functions:
        types.update(argument.type for argument in function.arguments)
        types.update(column.type for column in function.return_columns)
        if not function.return_columns:
            types.add(function.returns)
    types.discard("UNKNOWN")
    return tuple(sorted(types))
