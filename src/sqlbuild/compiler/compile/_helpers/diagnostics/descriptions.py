"""Require a non-empty description on every named project resource."""

from __future__ import annotations

import ast
import inspect
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from sqlbuild.compiler.compile.constants import MISSING_DESCRIPTION_CODE
from sqlbuild.compiler.compile.models import (
    CompileModelInput,
    CompilerDiagnostic,
    CompileSeedInput,
    CompileSourceInput,
    CompileSqlFunctionInput,
)
from sqlbuild.compiler.compile.types import (
    CompiledResourceType,
    DiagnosticPhase,
    DiagnosticSeverity,
    FunctionLanguage,
)
from sqlbuild.compiler.discovery.constants import PYTHON_UDF_DECORATOR_NAME, YAML_FILE_SUFFIXES
from sqlbuild.compiler.discovery.main._yaml_entry_line import yaml_entry_line
from sqlbuild.compiler.discovery.models import (
    DiscoveredLoaderFunction,
    DiscoveredProjectInputs,
    DiscoveredProvider,
)
from sqlbuild.compiler.sql_analysis.main._skip_block_comment import skip_block_comment
from sqlbuild.compiler.sql_analysis.main._skip_line_comment import skip_line_comment
from sqlbuild.errors.setting_help.main.join_helps import join_helps
from sqlbuild.errors.setting_help.main.snippet_help import snippet_help
from sqlbuild.spec.contracts.models import SourceLocation

_LINE_COMMENT_START: str = "--"
_BLOCK_COMMENT_START: str = "/*"


@dataclass(frozen=True)
class _Resource:
    """One named resource and the description it declares, if any."""

    kind: str
    name: str
    description: str | None
    location: Callable[[], SourceLocation]
    help: str
    resource_type: CompiledResourceType | None = None


@dataclass(frozen=True)
class _PythonNode:
    """The shared shape of a decorated Python node."""

    kind: str
    decorator: str
    name: str
    description: str | None
    relative_path: Path
    function: Callable[..., object]


def missing_description_diagnostics(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    model_inputs: tuple[CompileModelInput, ...],
    seed_inputs: tuple[CompileSeedInput, ...],
    source_inputs: tuple[CompileSourceInput, ...],
    function_inputs: tuple[CompileSqlFunctionInput, ...],
) -> tuple[CompilerDiagnostic, ...]:
    """Return one error for each named resource without a non-empty description."""

    loaders_by_name: dict[str, DiscoveredLoaderFunction] = {
        loader.name: loader for loader in discovered_inputs.loader_functions
    }
    resources: tuple[_Resource, ...] = (
        *(_model(model_input) for model_input in model_inputs),
        *_scenarios(discovered_inputs),
        *(_seed(seed_input) for seed_input in seed_inputs),
        *(
            _source(source_input=source_input, loaders_by_name=loaders_by_name)
            for source_input in source_inputs
        ),
        *(_function(function_input) for function_input in function_inputs),
        *_sql_hooks(discovered_inputs),
        *(
            _python_resource(node)
            for node in _python_nodes(
                discovered_inputs=discovered_inputs, source_inputs=source_inputs
            )
        ),
        *(_provider(provider) for provider in discovered_inputs.providers),
    )
    return tuple(
        _diagnostic(resource)
        for resource in resources
        if resource.description is None or not resource.description.strip()
    )


def _diagnostic(resource: _Resource) -> CompilerDiagnostic:
    state: str = (
        "has no description" if resource.description is None else "has an empty description"
    )
    return CompilerDiagnostic(
        phase=DiagnosticPhase.COMPILE,
        severity=DiagnosticSeverity.ERROR,
        code=MISSING_DESCRIPTION_CODE,
        message=f"{resource.kind} '{resource.name}' {state}",
        resource_type=resource.resource_type,
        resource_name=resource.name,
        location=resource.location(),
        help=resource.help,
    )


def _model(model_input: CompileModelInput) -> _Resource:
    name: str = model_input.model_file.file_path.stem
    path: Path = model_input.model_file.relative_path
    contents: str = model_input.model_file.contents
    help_text: str = _header_help(
        kind="model",
        name=name,
        statement="MODEL",
        entry=f'description "What one row of {name} represents"',
        path=path,
    )
    schema_entry_description: str | None = (
        model_input.schema_entry.description if model_input.schema_entry is not None else None
    )
    return _Resource(
        kind="model",
        name=name,
        description=schema_entry_description,
        location=partial(_header_location, path=path, contents=contents),
        help=help_text,
        resource_type=CompiledResourceType.MODEL,
    )


def _scenarios(discovered_inputs: DiscoveredProjectInputs) -> Iterator[_Resource]:
    for scenario_file in discovered_inputs.scenario_files:
        raw_description: object | None = scenario_file.header_values.get("description")
        yield _Resource(
            kind="scenario",
            name=scenario_file.name,
            description=raw_description if isinstance(raw_description, str) else None,
            location=partial(
                _header_location,
                path=scenario_file.relative_path,
                contents=scenario_file.contents,
            ),
            help=_header_help(
                kind="scenario",
                name=scenario_file.name,
                statement="SCENARIO",
                entry=f'description "The behaviour {scenario_file.name} proves"',
                path=scenario_file.relative_path,
            ),
            resource_type=CompiledResourceType.SQL_SCENARIO,
        )


def _seed(seed_input: CompileSeedInput) -> _Resource:
    name: str = seed_input.schema_entry.name
    return _Resource(
        kind="seed",
        name=name,
        description=seed_input.schema_entry.description,
        location=partial(
            _yaml_location,
            path=seed_input.schema_file.relative_path,
            contents=seed_input.schema_file.contents,
            name=name,
        ),
        help=_yaml_help(kind="seed", name=name, path=seed_input.schema_file.relative_path),
        resource_type=CompiledResourceType.SEED,
    )


def _source(
    *, source_input: CompileSourceInput, loaders_by_name: dict[str, DiscoveredLoaderFunction]
) -> _Resource:
    name: str = source_input.source_entry.name
    loader: DiscoveredLoaderFunction | None = (
        loaders_by_name.get(source_input.source_entry.loader)
        if source_input.source_entry.loader is not None
        else None
    )
    description: str | None = source_input.source_entry.description
    if (description is None or not description.strip()) and loader is not None:
        description = loader.description or description
    help_text: str = _yaml_help(
        kind="source", name=name, path=source_input.source_file.relative_path
    )
    if loader is not None and loader.relative_path.suffix not in YAML_FILE_SUFFIXES:
        help_text = join_helps(
            help_text,
            f"or describe its loader '{loader.name}' in {loader.relative_path.as_posix()} "
            f'with a docstring or @loader(description="What one row of {name} represents")',
        )
    return _Resource(
        kind="source",
        name=name,
        description=description,
        location=partial(
            _yaml_location,
            path=source_input.source_file.relative_path,
            contents=source_input.source_file.contents,
            name=name,
        ),
        help=help_text,
        resource_type=CompiledResourceType.SOURCE,
    )


def _function(function_input: CompileSqlFunctionInput) -> _Resource:
    name: str = function_input.name
    path: Path = function_input.function_file.relative_path
    resource_type: CompiledResourceType = (
        CompiledResourceType.TABLE_FN if function_input.return_columns else CompiledResourceType.UDF
    )
    location: Callable[[], SourceLocation]
    help_text: str
    if function_input.language == FunctionLanguage.PYTHON:
        location = partial(
            _decorator_location,
            path=path,
            contents=function_input.function_file.contents,
            decorator=PYTHON_UDF_DECORATOR_NAME,
        )
        help_text = snippet_help(
            purpose=f"to describe function '{name}'",
            target=f"give its function in {path.as_posix()} a docstring or add this to @udf",
            lines=(f'@udf(description="What {name} returns", ...)',),
        )
    else:
        location = partial(
            _header_location, path=path, contents=function_input.function_file.contents
        )
        help_text = _header_help(
            kind="function",
            name=name,
            statement="FUNCTION",
            entry=f'description "What {name} returns"',
            path=path,
        )
    return _Resource(
        kind="function",
        name=name,
        description=function_input.description,
        location=location,
        help=help_text,
        resource_type=resource_type,
    )


def _sql_hooks(discovered_inputs: DiscoveredProjectInputs) -> Iterator[_Resource]:
    for hook_file in discovered_inputs.sql_hook_files:
        yield _Resource(
            kind="hook",
            name=hook_file.name,
            description=hook_file.description,
            location=partial(
                _header_location, path=hook_file.relative_path, contents=hook_file.contents
            ),
            help=_header_help(
                kind="hook",
                name=hook_file.name,
                statement="HOOK",
                entry=f'description "What {hook_file.name} does"',
                path=hook_file.relative_path,
                description_only=True,
            ),
        )


def _python_nodes(
    *, discovered_inputs: DiscoveredProjectInputs, source_inputs: tuple[CompileSourceInput, ...]
) -> Iterator[_PythonNode]:
    source_owned_loaders: frozenset[str] = frozenset(
        source_input.source_entry.loader
        for source_input in source_inputs
        if source_input.source_entry.loader is not None
    )
    source_paths: frozenset[Path] = frozenset(
        source_file.relative_path for source_file in discovered_inputs.source_files
    )
    for loader in discovered_inputs.loader_functions:
        if loader.name in source_owned_loaders or loader.relative_path in source_paths:
            continue
        yield _PythonNode(
            kind="loader",
            decorator="loader",
            name=loader.name,
            description=loader.description,
            relative_path=loader.relative_path,
            function=loader.function,
        )
    for kind, functions in (
        ("task", discovered_inputs.task_functions),
        ("asset", discovered_inputs.asset_functions),
        ("check", discovered_inputs.check_functions),
        ("hook", discovered_inputs.hook_functions),
    ):
        for function in functions:
            yield _PythonNode(
                kind=kind,
                decorator=kind,
                name=function.name,
                description=function.description,
                relative_path=function.relative_path,
                function=function.function,
            )


def _python_resource(node: _PythonNode) -> _Resource:
    return _Resource(
        kind=node.kind,
        name=node.name,
        description=node.description,
        location=partial(_function_location, path=node.relative_path, function=node.function),
        help=snippet_help(
            purpose=f"to describe {node.kind} '{node.name}'",
            target=(
                f"give its function in {node.relative_path.as_posix()} a docstring "
                f"or pass a description to @{node.decorator}"
            ),
            lines=(f'@{node.decorator}(description="What {node.name} does", ...)',),
        ),
    )


def _provider(provider: DiscoveredProvider) -> _Resource:
    class_name: str = provider.provider_class.__name__
    raw_doc: object | None = provider.provider_class.__dict__.get("__doc__")
    return _Resource(
        kind="provider",
        name=provider.name,
        description=inspect.cleandoc(raw_doc) if isinstance(raw_doc, str) else None,
        location=partial(
            _class_location, path=provider.relative_path, provider_class=provider.provider_class
        ),
        help=snippet_help(
            purpose=f"to describe provider '{provider.name}'",
            target=f"add a class docstring in {provider.relative_path.as_posix()}",
            lines=(
                f"class {class_name}(Provider):",
                f'    """What {provider.name} provides."""',
            ),
        ),
    )


def _header_help(
    *,
    kind: str,
    name: str,
    statement: str,
    entry: str,
    path: Path,
    description_only: bool = False,
) -> str:
    lines: tuple[str, ...] = (
        (f"{statement} ({entry});",)
        if description_only
        else (f"{statement} (", f"  {entry},", "  ...", ");")
    )
    return snippet_help(
        purpose=f"to describe {kind} '{name}'",
        target=f"add this to the {statement} header in {path.as_posix()}",
        lines=lines,
    )


def _yaml_help(*, kind: str, name: str, path: Path) -> str:
    return snippet_help(
        purpose=f"to describe {kind} '{name}'",
        target=f"add `description` to its entry in {path.as_posix()}",
        lines=(f"- name: {name}", f"  description: What one row of {name} represents"),
    )


def _header_location(*, path: Path, contents: str) -> SourceLocation:
    """Locate the statement header: the first code after leading whitespace and comments."""

    position: int = 0
    while True:
        while position < len(contents) and contents[position].isspace():
            position += 1
        if contents.startswith(_LINE_COMMENT_START, position):
            position = skip_line_comment(sql=contents, start=position)
        elif contents.startswith(_BLOCK_COMMENT_START, position):
            position = skip_block_comment(sql=contents, start=position)
        else:
            return _offset_location(path=path, contents=contents, offset=position)


def _function_location(*, path: Path, function: Callable[..., object]) -> SourceLocation:
    return SourceLocation(path=path, line=_function_line(function), column=1)


def _class_location(*, path: Path, provider_class: type[object]) -> SourceLocation:
    return SourceLocation(path=path, line=_class_line(provider_class), column=1)


def _yaml_location(*, path: Path, contents: str, name: str) -> SourceLocation:
    line: int | None = yaml_entry_line(contents=contents, name=name)
    return SourceLocation(path=path, line=line or 1, column=1)


def _decorator_location(*, path: Path, contents: str, decorator: str) -> SourceLocation:
    """Locate the `@decorator` line of the decorated function, ignoring docstrings and comments."""

    try:
        module: ast.Module = ast.parse(contents)
    except SyntaxError:
        return SourceLocation(path=path, line=1, column=1)
    for node in ast.walk(module):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            for expression in node.decorator_list:
                if _decorator_name(expression) == decorator:
                    return SourceLocation(
                        path=path, line=expression.lineno, column=expression.col_offset
                    )
    return SourceLocation(path=path, line=1, column=1)


def _decorator_name(expression: ast.expr) -> str | None:
    target: ast.expr = expression.func if isinstance(expression, ast.Call) else expression
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    return None


def _offset_location(*, path: Path, contents: str, offset: int) -> SourceLocation:
    line: int = contents.count("\n", 0, offset) + 1
    column: int = offset - (contents.rfind("\n", 0, offset) + 1) + 1
    return SourceLocation(path=path, line=line, column=column)


def _function_line(function: Callable[..., object]) -> int:
    code: object | None = getattr(inspect.unwrap(function), "__code__", None)
    line: object | None = getattr(code, "co_firstlineno", None)
    return line if isinstance(line, int) else 1


def _class_line(provider_class: type[object]) -> int:
    try:
        return inspect.getsourcelines(provider_class)[1]
    except (OSError, TypeError):
        return 1
