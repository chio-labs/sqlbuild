"""Compile's explicit-reference checks: Python collects user-code owners, native decides."""

from __future__ import annotations

import inspect
import textwrap
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

import sqlbuild._native as _native
from sqlbuild._native import model_python_hook_names
from sqlbuild.compiler.compile.models import PythonSqlReferenceReport
from sqlbuild.compiler.compile.types import CompiledProjectView
from sqlbuild.compiler.discovery.main.explicit_references_help import explicit_references_help
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.references.types import HardCodedRelationOwnerKind
from sqlbuild.python_nodes.main.read_loader_definition import read_loader_definition
from sqlbuild.python_nodes.models import LoaderDefinition, SqlResourceRef
from sqlbuild.python_nodes.types import SqlResourceRefKind

_VALUE_PLACEHOLDER: str = "__sqlbuild_python_value_"


@dataclass(frozen=True)
class _PythonSqlOwner:
    label: str
    kind: HardCodedRelationOwnerKind
    function: Callable[..., object]
    relative_path: Path
    own_refs: frozenset[SqlResourceRef] = frozenset()
    upstream_loader_by_source: Mapping[str, str] = field(default_factory=dict)


def explicit_reference_report(
    *,
    project: CompiledProjectView,
    discovered_inputs: DiscoveredProjectInputs,
    enforce_explicit: bool,
) -> PythonSqlReferenceReport:
    """Return P005, P007 and P008 errors and unmatched Python-SQL relations; raise P001."""

    owners: tuple[_PythonSqlOwner, ...] = (
        _owners(project=project, discovered_inputs=discovered_inputs) if enforce_explicit else ()
    )
    paths: list[Path] = sorted({owner.relative_path for owner in owners})
    path_order: dict[Path, int] = {path: index for index, path in enumerate(paths)}
    return _native.explicit_reference_report(
        project,
        {
            "retains_old_names": discovered_inputs.project_config.migrations.old_name_views
            is not None,
            "enforce_explicit": enforce_explicit,
            "explicit_help": (
                explicit_references_help(allowed="hard-coded relation names")
                if enforce_explicit
                else ""
            ),
            "placeholder": _VALUE_PLACEHOLDER,
        },
        [
            (owner, path_order[owner.relative_path], _literal_sql_calls(owner.function))
            for owner in owners
        ],
    )


def _owners(
    *, project: CompiledProjectView, discovered_inputs: DiscoveredProjectInputs
) -> tuple[_PythonSqlOwner, ...]:
    owners: list[_PythonSqlOwner] = []
    for label, nodes in (
        ("task", discovered_inputs.task_functions),
        ("asset", discovered_inputs.asset_functions),
        ("check", discovered_inputs.check_functions),
    ):
        owners.extend(
            _PythonSqlOwner(
                label=f"{label}:{node.name}",
                kind=HardCodedRelationOwnerKind.NODE,
                function=node.function,
                relative_path=node.relative_path,
            )
            for node in nodes
        )
    owners.extend(_loader_owners(project=project, discovered_inputs=discovered_inputs))
    attached_models: dict[str, set[SqlResourceRef]] = {}
    for model in project.models:
        for hook_name in model_python_hook_names(model=model):
            attached_models.setdefault(hook_name, set()).add(
                SqlResourceRef(kind=SqlResourceRefKind.MODEL, name=model.name)
            )
    owners.extend(
        _PythonSqlOwner(
            label=f"hook:{hook.name}",
            kind=HardCodedRelationOwnerKind.HOOK,
            function=hook.function,
            relative_path=hook.relative_path,
            own_refs=frozenset(attached_models.get(hook.name, ())),
        )
        for hook in project.hook_functions
    )
    return tuple(owners)


def _loader_owners(
    *, project: CompiledProjectView, discovered_inputs: DiscoveredProjectInputs
) -> tuple[_PythonSqlOwner, ...]:
    sources_by_loader: dict[str, set[str]] = {}
    for source in project.sources:
        if source.source_entry.loader is not None:
            sources_by_loader.setdefault(source.source_entry.loader, set()).add(source.name)
    owners: list[_PythonSqlOwner] = []
    for loader in discovered_inputs.loader_functions:
        upstream_loader_by_source: dict[str, str] = {}
        for dependency in loader.depends_on:
            definition: LoaderDefinition | None = (
                read_loader_definition(dependency) if callable(dependency) else None
            )
            if definition is None:
                continue
            for source_name in sources_by_loader.get(definition.name, ()):
                upstream_loader_by_source[source_name] = getattr(
                    dependency, "__name__", definition.name
                )
        owners.append(
            _PythonSqlOwner(
                label=f"loader:{loader.name}",
                kind=HardCodedRelationOwnerKind.LOADER,
                function=loader.function,
                relative_path=loader.relative_path,
                own_refs=frozenset(
                    SqlResourceRef(kind=SqlResourceRefKind.SOURCE, name=source_name)
                    for source_name in sources_by_loader.get(loader.name, ())
                ),
                upstream_loader_by_source=upstream_loader_by_source,
            )
        )
    return tuple(owners)


def _literal_sql_calls(function: Callable[..., object]) -> list[tuple[str, str, int]]:
    try:
        lines: list[str]
        start_line: int
        lines, start_line = inspect.getsourcelines(function)
    except (OSError, TypeError):
        return []
    return _native.python_literal_sql_calls(
        textwrap.dedent("".join(lines)), start_line, _VALUE_PLACEHOLDER
    )
