"""Compile-time expansion helpers for authored project SQL macros."""

from __future__ import annotations

import ast
import importlib.util
import inspect
import re
from importlib.machinery import ModuleSpec
from pathlib import Path
from types import ModuleType

from sqlbuild.compiler.compile.constants import MACRO_CALL_PATTERN
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models.core import (
    LoadedMacro,
    MacroContext,
)
from sqlbuild.compiler.discovery.models import DiscoveredMacroFile
from sqlbuild.compiler.shared.helpers.sql_scanning import (
    find_matching_paren,
    skip_block_comment,
    skip_line_comment,
    skip_quoted_text,
)
from sqlbuild.compiler.shared.helpers.sql_scanning import (
    is_identifier_character as _is_identifier_continue,
)
from sqlbuild.compiler.shared.helpers.sql_scanning import (
    is_identifier_start as _is_identifier_start,
)

_CONTEXT: str = "Macro expansion"


def load_project_macros(macro_files: tuple[DiscoveredMacroFile, ...]) -> dict[str, LoadedMacro]:
    """Load discovered project macro functions into a collision-checked registry."""

    loaded_macros: dict[str, LoadedMacro] = {}
    macro_file: DiscoveredMacroFile
    for macro_file in macro_files:
        module: ModuleType = _load_macro_module(macro_file=macro_file)
        attribute_name: str
        for attribute_name in dir(module):
            if attribute_name.startswith("_"):
                continue
            attribute_value: object = getattr(module, attribute_name)
            if not callable(attribute_value):
                continue
            existing_macro: LoadedMacro | None = loaded_macros.get(attribute_name)
            if existing_macro is not None:
                raise CompileInputError(
                    f"Macro name collision for '{attribute_name}': "
                    f"{existing_macro.file_path} and {macro_file.file_path}"
                )
            loaded_macros[attribute_name] = LoadedMacro(
                name=attribute_name,
                file_path=macro_file.file_path,
                relative_path=macro_file.relative_path,
                raw_source=macro_file.contents,
                function=attribute_value,
            )
    return loaded_macros


def expand_sql_macros(
    *,
    sql: str,
    file_path: Path,
    loaded_macros: dict[str, LoadedMacro],
    macro_overrides: dict[str, str] | None = None,
    macro_context: MacroContext,
) -> str:
    """Expand authored Python macros in one executable SQL string."""

    if "@" not in sql:
        return sql

    rendered_sql_parts: list[str] = []
    cursor: int = 0
    while cursor < len(sql):
        macro_start_index: int | None = _find_next_macro_start(sql=sql, start_index=cursor)
        if macro_start_index is None:
            rendered_sql_parts.append(sql[cursor:])
            break
        rendered_sql_parts.append(sql[cursor:macro_start_index])
        macro_result: object
        next_index: int
        macro_result, next_index = _evaluate_macro_call(
            sql=sql,
            call_start_index=macro_start_index,
            file_path=file_path,
            loaded_macros=loaded_macros,
            macro_overrides={} if macro_overrides is None else macro_overrides,
            macro_context=macro_context,
            top_level=True,
        )
        if not isinstance(macro_result, str):
            raise CompileInputError(
                f"Macro '@{_parse_macro_name(sql=sql, call_start_index=macro_start_index)}' in "
                f"'{file_path}' must return a SQL string when used directly in SQL"
            )
        matched_call: re.Match[str] | None = MACRO_CALL_PATTERN.search(macro_result)
        if matched_call is not None:
            raise CompileInputError(
                f"Macro expansion in '{file_path}' produced output containing unexpanded macro "
                f"call '{matched_call.group(0).rstrip()}'. Compose macros in Python instead."
            )
        rendered_sql_parts.append(macro_result)
        cursor = next_index
    return "".join(rendered_sql_parts)


def find_macro_call_names(sql: str) -> tuple[str, ...]:
    """Return unique authored macro call names in encounter order."""

    names: list[str] = []
    seen: set[str] = set()
    cursor: int = 0
    while cursor < len(sql):
        macro_start_index: int | None = _find_next_macro_start(sql=sql, start_index=cursor)
        if macro_start_index is None:
            break
        macro_name: str = _parse_macro_name(sql=sql, call_start_index=macro_start_index)
        if macro_name not in seen:
            seen.add(macro_name)
            names.append(macro_name)
        opening_paren_index: int = _skip_whitespace(sql, macro_start_index + 1 + len(macro_name))
        cursor = _find_matching_paren(sql=sql, opening_paren_index=opening_paren_index) + 1
    return tuple(names)


def _load_macro_module(*, macro_file: DiscoveredMacroFile) -> ModuleType:
    module_name: str = "sqlbuild_project_macro_" + "_".join(
        macro_file.relative_path.with_suffix("").parts
    ).replace("-", "_")
    spec: ModuleSpec | None = importlib.util.spec_from_file_location(
        module_name, macro_file.file_path
    )
    if spec is None or spec.loader is None:
        raise CompileInputError(f"Could not load macros from '{macro_file.file_path}'")
    module: ModuleType = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as error:
        raise CompileInputError(
            f"Failed to load macros from '{macro_file.file_path}': {error}"
        ) from error
    return module


def _evaluate_macro_call(
    *,
    sql: str,
    call_start_index: int,
    file_path: Path,
    loaded_macros: dict[str, LoadedMacro],
    macro_overrides: dict[str, str],
    macro_context: MacroContext,
    top_level: bool,
) -> tuple[object, int]:
    macro_name: str = _parse_macro_name(sql=sql, call_start_index=call_start_index)
    loaded_macro: LoadedMacro | None = loaded_macros.get(macro_name)
    override_value: str | None = macro_overrides.get(macro_name)
    if loaded_macro is None and override_value is None:
        available_macro_names: str = ", ".join(sorted(loaded_macros)) or "none"
        raise CompileInputError(
            f"Unknown macro '@{macro_name}' in '{file_path}'. Available macros: "
            f"{available_macro_names}"
        )
    opening_paren_index: int = _skip_whitespace(sql, call_start_index + 1 + len(macro_name))
    closing_paren_index: int = _find_matching_paren(
        sql=sql, opening_paren_index=opening_paren_index
    )
    if override_value is not None:
        return override_value, closing_paren_index + 1
    if loaded_macro is None:
        raise CompileInputError("loaded macro is unexpectedly missing after validation")
    args_source: str = sql[opening_paren_index + 1 : closing_paren_index]
    args: tuple[object, ...]
    kwargs: dict[str, object]
    args, kwargs = _parse_macro_arguments(
        args_source=args_source,
        file_path=file_path,
        loaded_macros=loaded_macros,
        macro_overrides=macro_overrides,
        macro_context=macro_context,
    )
    try:
        macro_result: object = _call_loaded_macro(
            loaded_macro=loaded_macro,
            macro_context=macro_context,
            args=args,
            kwargs=kwargs,
        )
    except TypeError as error:
        raise CompileInputError(
            f"Macro '@{macro_name}' in '{file_path}' could not be called: {error}"
        ) from error
    except Exception as error:
        raise CompileInputError(
            f"Macro '@{macro_name}' in '{file_path}' failed: {error}"
        ) from error
    if top_level and not isinstance(macro_result, str):
        raise CompileInputError(
            f"Macro '@{macro_name}' in '{file_path}' must return a SQL string when "
            "used directly in SQL"
        )
    return macro_result, closing_paren_index + 1


def _call_loaded_macro(
    *,
    loaded_macro: LoadedMacro,
    macro_context: MacroContext,
    args: tuple[object, ...],
    kwargs: dict[str, object],
) -> object:
    signature: inspect.Signature = inspect.signature(loaded_macro.function)
    parameters: tuple[inspect.Parameter, ...] = tuple(signature.parameters.values())
    if (
        parameters
        and parameters[0].kind
        in {inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD}
        and parameters[0].name == "ctx"
    ):
        if "ctx" in kwargs:
            raise CompileInputError(
                f"Macro '@{loaded_macro.name}' must not be called with keyword argument 'ctx'; "
                "'ctx' is reserved for injected macro context"
            )
        return loaded_macro.function(macro_context, *args, **kwargs)
    return loaded_macro.function(*args, **kwargs)


def _parse_macro_arguments(
    *,
    args_source: str,
    file_path: Path,
    loaded_macros: dict[str, LoadedMacro],
    macro_overrides: dict[str, str],
    macro_context: MacroContext,
) -> tuple[tuple[object, ...], dict[str, object]]:
    if not args_source.strip():
        return (), {}
    rewritten_args_source: str
    placeholder_values: dict[str, object]
    rewritten_args_source, placeholder_values = _rewrite_nested_macro_calls(
        args_source=args_source,
        file_path=file_path,
        loaded_macros=loaded_macros,
        macro_overrides=macro_overrides,
        macro_context=macro_context,
    )
    try:
        expression: ast.Expression = ast.parse(f"_macro_call({rewritten_args_source})", mode="eval")
    except SyntaxError as error:
        raise CompileInputError(
            f"Macro arguments in '{file_path}' could not be parsed: {error}"
        ) from error
    if not isinstance(expression.body, ast.Call):
        raise CompileInputError(f"Macro arguments in '{file_path}' could not be parsed")
    call_expression: ast.Call = expression.body
    args: tuple[object, ...] = tuple(
        _evaluate_literal_ast_node(
            node=argument,
            placeholder_values=placeholder_values,
            file_path=file_path,
        )
        for argument in call_expression.args
    )
    kwargs: dict[str, object] = {}
    keyword: ast.keyword
    for keyword in call_expression.keywords:
        if keyword.arg is None:
            raise CompileInputError(
                f"Macro arguments in '{file_path}' must not use **kwargs expansion syntax"
            )
        kwargs[keyword.arg] = _evaluate_literal_ast_node(
            node=keyword.value,
            placeholder_values=placeholder_values,
            file_path=file_path,
        )
    return args, kwargs


def _rewrite_nested_macro_calls(
    *,
    args_source: str,
    file_path: Path,
    loaded_macros: dict[str, LoadedMacro],
    macro_overrides: dict[str, str],
    macro_context: MacroContext,
) -> tuple[str, dict[str, object]]:
    rewritten_parts: list[str] = []
    placeholder_values: dict[str, object] = {}
    cursor: int = 0
    replacement_index: int = 0
    while cursor < len(args_source):
        macro_start_index: int | None = _find_next_macro_start(sql=args_source, start_index=cursor)
        if macro_start_index is None:
            rewritten_parts.append(args_source[cursor:])
            break
        rewritten_parts.append(args_source[cursor:macro_start_index])
        nested_result: object
        next_index: int
        nested_result, next_index = _evaluate_macro_call(
            sql=args_source,
            call_start_index=macro_start_index,
            file_path=file_path,
            loaded_macros=loaded_macros,
            macro_overrides=macro_overrides,
            macro_context=macro_context,
            top_level=False,
        )
        placeholder: str = f"__sqlbuild_macro_arg_{replacement_index}"
        replacement_index += 1
        placeholder_values[placeholder] = nested_result
        rewritten_parts.append(placeholder)
        cursor = next_index
    return "".join(rewritten_parts), placeholder_values


def _evaluate_literal_ast_node(
    *,
    node: ast.AST,
    placeholder_values: dict[str, object],
    file_path: Path,
) -> object:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in placeholder_values:
            return placeholder_values[node.id]
        if node.id in {"True", "False", "None"}:
            return ast.literal_eval(node)
    if isinstance(node, ast.List):
        return [
            _evaluate_literal_ast_node(
                node=element,
                placeholder_values=placeholder_values,
                file_path=file_path,
            )
            for element in node.elts
        ]
    if isinstance(node, ast.Tuple):
        return tuple(
            _evaluate_literal_ast_node(
                node=element,
                placeholder_values=placeholder_values,
                file_path=file_path,
            )
            for element in node.elts
        )
    if isinstance(node, ast.Dict):
        return {
            _evaluate_dict_key_ast_node(
                key_node=key,
                placeholder_values=placeholder_values,
                file_path=file_path,
            ): _evaluate_literal_ast_node(
                node=value,
                placeholder_values=placeholder_values,
                file_path=file_path,
            )
            for key, value in zip(node.keys, node.values, strict=True)
        }
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        operand: object = _evaluate_literal_ast_node(
            node=node.operand,
            placeholder_values=placeholder_values,
            file_path=file_path,
        )
        if not isinstance(operand, int | float):
            raise CompileInputError(f"Macro arguments in '{file_path}' use unsupported unary value")
        return -operand if isinstance(node.op, ast.USub) else operand
    raise CompileInputError(
        f"Macro arguments in '{file_path}' must use only Python literals and nested macro calls"
    )


def _evaluate_dict_key_ast_node(
    *,
    key_node: ast.AST | None,
    placeholder_values: dict[str, object],
    file_path: Path,
) -> object:
    if key_node is None:
        raise CompileInputError(f"Macro arguments in '{file_path}' must not use dict unpacking")
    return _evaluate_literal_ast_node(
        node=key_node,
        placeholder_values=placeholder_values,
        file_path=file_path,
    )


def _find_next_macro_start(*, sql: str, start_index: int) -> int | None:
    index: int = start_index
    while index < len(sql):
        character: str = sql[index]
        if character in {"'", '"', "`"}:
            index = skip_quoted_text(sql=sql, start=index, context=_CONTEXT)
            continue
        if sql.startswith("--", index):
            index = skip_line_comment(sql=sql, start=index)
            continue
        if sql.startswith("/*", index):
            index = skip_block_comment(sql=sql, start=index, context=_CONTEXT)
            continue
        if character == "@" and _is_macro_call_start(sql=sql, at_index=index):
            return index
        index += 1
    return None


def _is_macro_call_start(*, sql: str, at_index: int) -> bool:
    if at_index + 1 >= len(sql) or not _is_identifier_start(sql[at_index + 1]):
        return False
    cursor: int = at_index + 2
    while cursor < len(sql) and _is_identifier_continue(sql[cursor]):
        cursor += 1
    cursor = _skip_whitespace(sql, cursor)
    return cursor < len(sql) and sql[cursor] == "("


def _parse_macro_name(*, sql: str, call_start_index: int) -> str:
    cursor: int = call_start_index + 1
    while cursor < len(sql) and _is_identifier_continue(sql[cursor]):
        cursor += 1
    return sql[call_start_index + 1 : cursor]


def _find_matching_paren(*, sql: str, opening_paren_index: int) -> int:
    if opening_paren_index >= len(sql) or sql[opening_paren_index] != "(":
        raise CompileInputError("expected opening parenthesis")
    return find_matching_paren(sql=sql, open_paren_index=opening_paren_index, context=_CONTEXT)


def _skip_whitespace(sql: str, start_index: int) -> int:
    index: int = start_index
    while index < len(sql) and sql[index].isspace():
        index += 1
    return index
