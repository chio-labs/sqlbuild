"""Rows the native resource diagnostics read: loaders and user Python resources."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterator
from functools import partial
from pathlib import Path

from sqlbuild.compiler.compile.types import SourceInput
from sqlbuild.compiler.compiled_project.types import PythonResourceRow
from sqlbuild.compiler.discovery.constants import YAML_FILE_SUFFIXES
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs, DiscoveredProvider
from sqlbuild.errors.setting_help.main.snippet_help import snippet_help
from sqlbuild.spec.contracts.models import SourceLocation


def loader_rows(discovered_inputs: DiscoveredProjectInputs) -> dict[str, tuple[object, ...]]:
    """Each loader's description, relative path and whether that path is a YAML file."""

    return {
        loader.name: (
            loader.description,
            str(loader.relative_path),
            loader.relative_path.suffix in YAML_FILE_SUFFIXES,
        )
        for loader in discovered_inputs.loader_functions
    }


def python_resource_rows(
    *, discovered_inputs: DiscoveredProjectInputs, source_inputs: tuple[SourceInput, ...]
) -> list[PythonResourceRow]:
    """User Python loaders, tasks, assets, checks and hooks, then providers, in report order."""

    return [
        *_python_nodes(discovered_inputs=discovered_inputs, source_inputs=source_inputs),
        *(_provider(provider) for provider in discovered_inputs.providers),
    ]


def _python_nodes(
    *, discovered_inputs: DiscoveredProjectInputs, source_inputs: tuple[SourceInput, ...]
) -> Iterator[PythonResourceRow]:
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
        yield _python_resource(
            kind="loader",
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
            yield _python_resource(
                kind=kind,
                name=function.name,
                description=function.description,
                relative_path=function.relative_path,
                function=function.function,
            )


def _python_resource(
    *,
    kind: str,
    name: str,
    description: str | None,
    relative_path: Path,
    function: Callable[..., object],
) -> PythonResourceRow:
    return (
        kind,
        name,
        description,
        partial(_function_location, path=relative_path, function=function),
        snippet_help(
            purpose=f"to describe {kind} '{name}'",
            target=(
                f"give its function in {relative_path.as_posix()} a docstring "
                f"or pass a description to @{kind}"
            ),
            lines=(f'@{kind}(description="What {name} does", ...)',),
        ),
    )


def _provider(provider: DiscoveredProvider) -> PythonResourceRow:
    class_name: str = provider.provider_class.__name__
    raw_doc: object | None = provider.provider_class.__dict__.get("__doc__")
    return (
        "provider",
        provider.name,
        inspect.cleandoc(raw_doc) if isinstance(raw_doc, str) else None,
        partial(
            _class_location, path=provider.relative_path, provider_class=provider.provider_class
        ),
        snippet_help(
            purpose=f"to describe provider '{provider.name}'",
            target=f"add a class docstring in {provider.relative_path.as_posix()}",
            lines=(
                f"class {class_name}(Provider):",
                f'    """What {provider.name} provides."""',
            ),
        ),
    )


def _function_location(*, path: Path, function: Callable[..., object]) -> SourceLocation:
    code: object | None = getattr(inspect.unwrap(function), "__code__", None)
    line: object | None = getattr(code, "co_firstlineno", None)
    return SourceLocation(path=path, line=line if isinstance(line, int) else 1, column=1)


def _class_location(*, path: Path, provider_class: type[object]) -> SourceLocation:
    try:
        line: int = inspect.getsourcelines(provider_class)[1]
    except (OSError, TypeError):
        line = 1
    return SourceLocation(path=path, line=line, column=1)
