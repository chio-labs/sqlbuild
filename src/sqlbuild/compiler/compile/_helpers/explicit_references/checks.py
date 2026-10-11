"""Compile's explicit-reference checks: Python collects the facts, native decides."""

from __future__ import annotations

import ast
import inspect
import textwrap
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from itertools import chain
from pathlib import Path
from typing import Any

import orjson

import sqlbuild._native as _native
from sqlbuild.compiler.compile.constants import MIGRATE_FROM_CONFIG_KEY
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import (
    CompiledObjectKey,
    CompiledRelationLocation,
    CompilerDiagnostic,
    PythonSqlReferenceReport,
)
from sqlbuild.compiler.compile.types import (
    AttachedAuditTargetKind,
    CompiledAuditView,
    CompiledModelView,
    CompiledProjectView,
    CompiledSourceView,
    DiagnosticPhase,
    DiagnosticSeverity,
)
from sqlbuild.compiler.discovery.main.explicit_references_help import explicit_references_help
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs, SqlHookEntry
from sqlbuild.compiler.graph.main._model_python_hook_names import model_python_hook_names
from sqlbuild.compiler.migrations.main._resolve_old_name_view_retention import (
    resolve_old_name_view_retention,
)
from sqlbuild.compiler.references.models import LiteralSqlRelation, RelationName
from sqlbuild.compiler.references.types import HardCodedRelationOwnerKind
from sqlbuild.python_nodes.main.read_loader_definition import read_loader_definition
from sqlbuild.python_nodes.models import LoaderDefinition, SqlResourceRef
from sqlbuild.python_nodes.types import SqlResourceRefKind
from sqlbuild.spec.contracts.models import SourceEntry, SourceLocation

_MODEL_HOOK_KEYS: tuple[str, ...] = ("pre_hooks", "post_hooks")
_RAISE_KEY: str = "raise"
_REPORT_KEY: str = "report"
_SQL_METHOD_NAMES: frozenset[str] = frozenset({"query", "execute_sql"})
_SQL_PARAMETER_NAME: str = "sql"
_CONTEXT_PARAMETER_NAMES: frozenset[str] = frozenset({"ctx", "context", "_ctx", "hook_context"})
_VALUE_PLACEHOLDER: str = "__sqlbuild_python_value_"


@dataclass(frozen=True)
class _PythonSqlOwner:
    label: str
    kind: HardCodedRelationOwnerKind
    function: Callable[..., object]
    relative_path: Path
    own_refs: frozenset[SqlResourceRef] = frozenset()
    upstream_loader_by_source: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class _LiteralSql:
    method: str
    sql: str
    line: int


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
    literals: tuple[tuple[_LiteralSql, ...], ...] = tuple(
        tuple(_literal_sql_calls(owner.function)) for owner in owners
    )
    paths: list[Path] = sorted({owner.relative_path for owner in owners})
    path_order: dict[Path, int] = {path: index for index, path in enumerate(paths)}
    outcome: dict[str, Any] = orjson.loads(
        _native.check_native_explicit_references(
            orjson.dumps(
                {
                    "enforce_explicit": enforce_explicit,
                    "dialect": project.sql_analysis_dialect,
                    "explicit_help": (
                        explicit_references_help(allowed="hard-coded relation names")
                        if enforce_explicit
                        else ""
                    ),
                    "placeholder": _VALUE_PLACEHOLDER,
                    "resources": _resource_rows(project),
                    "models": [
                        _model_row(
                            model=model,
                            old_name_retention=(
                                discovered_inputs.project_config.migrations.old_name_views
                            ),
                        )
                        for model in project.models
                    ],
                    "sources": [_source_row(source) for source in project.sources],
                    "seeds": [
                        {
                            "name": seed.name,
                            "relation": _location_row(seed.destination),
                        }
                        for seed in project.seeds
                    ],
                    "audits": [_audit_row(audit) for audit in project.audits],
                    "hooks": [
                        {
                            "name": hook.name,
                            "path": hook.relative_path.as_posix(),
                            "reads": _ref_rows(hook.reads),
                        }
                        for hook in project.hook_functions
                    ],
                    "owners": [
                        _owner_row(
                            owner=owner,
                            literals=owner_literals,
                            path_order=path_order[owner.relative_path],
                        )
                        for owner, owner_literals in zip(owners, literals, strict=True)
                    ],
                }
            ).decode()
        )
    )
    if _RAISE_KEY in outcome:
        raise CompileInputError(outcome[_RAISE_KEY])
    report: dict[str, Any] = outcome[_REPORT_KEY]
    return PythonSqlReferenceReport(
        diagnostics=tuple(_diagnostic(row=row, owners=owners) for row in report["diagnostics"]),
        unmatched=tuple(
            LiteralSqlRelation(
                owner_label=owners[row["owner"]].label,
                owner_kind=owners[row["owner"]].kind,
                relative_path=owners[row["owner"]].relative_path,
                line=row["line"],
                method=row["method"],
                relation=RelationName(
                    name=row["relation"]["name"],
                    schema=row["relation"]["schema"],
                    database=row["relation"]["database"],
                ),
            )
            for row in report["unmatched"]
        ),
    )


def _diagnostic(*, row: dict[str, Any], owners: tuple[_PythonSqlOwner, ...]) -> CompilerDiagnostic:
    owner: int | None = row["owner"]
    resource: list[str] | None = row["resource"]
    return CompilerDiagnostic(
        phase=DiagnosticPhase.COMPILE,
        severity=DiagnosticSeverity.ERROR,
        code=row["code"],
        message=row["message"],
        resource_type=None if resource is None else resource[0],
        resource_name=None if resource is None else resource[1],
        path=None if row["path"] is None else Path(row["path"]),
        location=(
            None
            if owner is None
            else SourceLocation(path=owners[owner].relative_path, line=row["line"], column=1)
        ),
        help=row["help"],
    )


def _owner_row(
    *, owner: _PythonSqlOwner, literals: tuple[_LiteralSql, ...], path_order: int
) -> dict[str, object]:
    return {
        "label": owner.label,
        "kind": str(owner.kind),
        "path_order": path_order,
        "own_refs": _ref_rows(tuple(owner.own_refs)),
        "upstream_loaders": list(owner.upstream_loader_by_source.items()),
        "literals": [
            {"method": literal.method, "sql": literal.sql, "line": literal.line}
            for literal in literals
        ],
    }


def _resource_rows(project: CompiledProjectView) -> list[dict[str, object]]:
    return [
        *(_graph_row(key=model.key_row, deps=model.dep_rows) for model in project.models),
        *(
            _graph_row(key=_key_row(resource.key), deps=_key_rows(resource.deps))
            for resource in (*project.sources, *project.seeds, *project.functions)
        ),
    ]


def _graph_row(*, key: tuple[str, str], deps: list[tuple[str, str]]) -> dict[str, object]:
    return {"key": key, "deps": deps}


def _key_row(key: CompiledObjectKey) -> tuple[str, str]:
    return (str(key.resource_type), key.name)


def _key_rows(keys: tuple[CompiledObjectKey, ...]) -> list[tuple[str, str]]:
    return [_key_row(key) for key in keys]


def _model_row(*, model: CompiledModelView, old_name_retention: str | None) -> dict[str, object]:
    raw: object = model.config.values.get(MIGRATE_FROM_CONFIG_KEY)
    retained: bool = isinstance(raw, str) and (
        resolve_old_name_view_retention(
            config_values=model.config.values, project_retention=old_name_retention
        )
        is not None
    )
    return {
        "name": model.name,
        "path": str(model.relative_path),
        "destination": _destination_row(model.destination_row),
        "python_hooks": list(model_python_hook_names(model=model)),
        "sql_hooks": list(
            chain.from_iterable(
                _sql_hook_rows(hook_key=hook_key, entries=model.config.values.get(hook_key))
                for hook_key in _MODEL_HOOK_KEYS
            )
        ),
        "migrate_from": raw if retained else None,
    }


def _sql_hook_rows(*, hook_key: str, entries: object) -> list[dict[str, object]]:
    """SQL hook entries with declared reads, at their position among the key's entries."""

    items: tuple[object, ...] = tuple(entries) if isinstance(entries, list | tuple) else (entries,)
    return [
        {
            "hook_key": hook_key,
            "index": index,
            "name": entry.name,
            "path": None if entry.relative_path is None else str(entry.relative_path),
            "reads": _ref_rows(entry.reads),
        }
        for index, entry in enumerate(items)
        if isinstance(entry, SqlHookEntry) and entry.reads
    ]


def _source_row(source: CompiledSourceView) -> dict[str, object]:
    entry: SourceEntry = source.source_entry
    return {
        "name": source.name,
        "table": entry.table,
        "schema": entry.schema,
        "database": entry.database,
        "expression": entry.expression is not None,
    }


def _audit_row(audit: CompiledAuditView) -> dict[str, object]:
    target: tuple[str, str] | None = (
        (
            str(AttachedAuditTargetKind(audit.attached_target_kind).resource_type),
            audit.attached_target_name,
        )
        if audit.attached_target_kind is not None and audit.attached_target_name is not None
        else None
    )
    return {
        "name": audit.name,
        "path": str(audit.audit_file.relative_path),
        "target": target,
        "scope_deps": _key_rows(audit.scope_deps),
    }


def _location_row(location: CompiledRelationLocation) -> dict[str, str | None]:
    return _destination_row((location.database, location.schema, location.name))


def _destination_row(row: tuple[str | None, str | None, str]) -> dict[str, str | None]:
    database, schema, name = row
    return {"name": name, "schema": schema, "database": database}


def _ref_rows(refs: tuple[SqlResourceRef, ...]) -> list[tuple[str, str]]:
    return [(str(ref.kind), ref.name) for ref in refs]


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


def _literal_sql_calls(function: Callable[..., object]) -> Iterator[_LiteralSql]:
    try:
        lines: list[str]
        start_line: int
        lines, start_line = inspect.getsourcelines(function)
        tree: ast.Module = ast.parse(textwrap.dedent("".join(lines)))
    except (OSError, TypeError, SyntaxError):
        return
    definition: ast.stmt | None = tree.body[0] if tree.body else None
    if not isinstance(definition, ast.FunctionDef | ast.AsyncFunctionDef):
        return
    parameters: list[str] = [
        argument.arg
        for argument in (
            *definition.args.posonlyargs,
            *definition.args.args,
            *definition.args.kwonlyargs,
        )
    ]
    context_name: str | None = next(
        (name for name in parameters if name in _CONTEXT_PARAMETER_NAMES),
        parameters[0] if parameters else None,
    )
    if context_name is None:
        return
    for node in ast.walk(definition):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _SQL_METHOD_NAMES
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == context_name
        ):
            continue
        argument: ast.expr | None = _sql_argument(node)
        sql: str | None = _literal_text(argument) if argument is not None else None
        if sql is not None:
            yield _LiteralSql(method=node.func.attr, sql=sql, line=start_line + node.lineno - 1)


def _sql_argument(call: ast.Call) -> ast.expr | None:
    if call.args:
        return call.args[0]
    for keyword in call.keywords:
        if keyword.arg == _SQL_PARAMETER_NAME:
            return keyword.value
        if keyword.arg is None and isinstance(keyword.value, ast.Dict):
            for key, value in zip(keyword.value.keys, keyword.value.values, strict=True):
                if isinstance(key, ast.Constant) and key.value == _SQL_PARAMETER_NAME:
                    return value
    return None


def _literal_text(node: ast.expr) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if not isinstance(node, ast.JoinedStr):
        return None
    parts: list[str] = []
    for index, value in enumerate(node.values):
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            parts.append(value.value)
        else:
            parts.append(f"{_VALUE_PLACEHOLDER}{index}")
    return "".join(parts)
