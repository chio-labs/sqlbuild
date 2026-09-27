"""Compile-time rejection of project relation names hard-coded in Python SQL."""

from __future__ import annotations

import ast
import inspect
import textwrap
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

from sqlbuild.compiler.compile.constants import HARD_CODED_PROJECT_RELATION_CODE
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.graph.main._model_python_hook_names import model_python_hook_names
from sqlbuild.compiler.references.main._compiled_project_relations import (
    compiled_project_relations,
)
from sqlbuild.compiler.references.main.extract_relation_names import extract_relation_names
from sqlbuild.compiler.references.main.match_project_relation import match_project_relation
from sqlbuild.compiler.references.models import (
    ProjectRelation,
    ProjectRelationIndex,
    RelationName,
)
from sqlbuild.python_nodes.models import SqlResourceRef
from sqlbuild.python_nodes.types import SqlResourceRefKind

_SQL_METHOD_NAMES: frozenset[str] = frozenset({"query", "execute_sql"})
_CONTEXT_PARAMETER_NAMES: frozenset[str] = frozenset({"ctx", "context", "_ctx", "hook_context"})
_VALUE_PLACEHOLDER: str = "__sqlbuild_python_value_"


@dataclass(frozen=True)
class _PythonSqlOwner:
    label: str
    function: Callable[..., object]
    relative_path: Path
    declare_help: str
    own_refs: frozenset[SqlResourceRef]
    relation_kinds: frozenset[SqlResourceRefKind]


@dataclass(frozen=True)
class _LiteralSql:
    method: str
    sql: str
    line: int


def validate_python_sql_references(
    *, project: CompiledProject, discovered_inputs: DiscoveredProjectInputs
) -> None:
    """Reject literal SQL in tasks, assets, and hooks that names a project relation."""

    owners: tuple[_PythonSqlOwner, ...] = _owners(
        project=project, discovered_inputs=discovered_inputs
    )
    if not owners:
        return
    index: ProjectRelationIndex = compiled_project_relations(project=project)
    if not index.relations:
        return
    for owner in owners:
        temporary: frozenset[str] = frozenset()
        for literal in sorted(_literal_sql_calls(owner.function), key=lambda item: item.line):
            temporary = _reject_hard_coded_relation(
                owner=owner,
                literal=literal,
                index=index,
                dialect=project.sql_analysis_dialect,
                temporary=temporary,
            )


def _owners(
    *, project: CompiledProject, discovered_inputs: DiscoveredProjectInputs
) -> tuple[_PythonSqlOwner, ...]:
    node_kinds: frozenset[SqlResourceRefKind] = frozenset(
        {SqlResourceRefKind.MODEL, SqlResourceRefKind.SOURCE}
    )
    owners: list[_PythonSqlOwner] = []
    for label, nodes in (
        ("task", discovered_inputs.task_functions),
        ("asset", discovered_inputs.asset_functions),
    ):
        owners.extend(
            _PythonSqlOwner(
                label=f"{label}:{node.name}",
                function=node.function,
                relative_path=node.relative_path,
                declare_help="declare it with depends_on={typed}",
                own_refs=frozenset(),
                relation_kinds=node_kinds,
            )
            for node in nodes
        )
    attached_models: dict[str, set[SqlResourceRef]] = {}
    for model in project.models:
        for hook_name in model_python_hook_names(model=model):
            attached_models.setdefault(hook_name, set()).add(
                SqlResourceRef(kind=SqlResourceRefKind.MODEL, name=model.name)
            )
    owners.extend(
        _PythonSqlOwner(
            label=f"hook:{hook.name}",
            function=hook.function,
            relative_path=hook.relative_path,
            declare_help="declare it with @hook(reads={typed})",
            own_refs=frozenset(attached_models.get(hook.name, ())),
            relation_kinds=frozenset(SqlResourceRefKind),
        )
        for hook in project.hook_functions
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
            and node.args
        ):
            continue
        sql: str | None = _literal_text(node.args[0])
        if sql is not None:
            yield _LiteralSql(method=node.func.attr, sql=sql, line=start_line + node.lineno - 1)


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


def _reject_hard_coded_relation(
    *,
    owner: _PythonSqlOwner,
    literal: _LiteralSql,
    index: ProjectRelationIndex,
    dialect: str | None,
    temporary: frozenset[str],
) -> frozenset[str]:
    extracted: tuple[tuple[RelationName, ...], frozenset[str]] | None = extract_relation_names(
        sql=literal.sql, dialect=dialect
    )
    if extracted is None:
        return temporary
    relations, created = extracted
    temporary = temporary | created
    for relation in relations:
        if _VALUE_PLACEHOLDER in "".join(
            part for part in (relation.database, relation.schema, relation.name) if part
        ):
            continue
        if relation.schema is None and relation.name.casefold() in temporary:
            continue
        match: ProjectRelation | None = match_project_relation(index=index, relation=relation)
        if (
            match is None
            or match.ref in owner.own_refs
            or match.ref.kind not in owner.relation_kinds
        ):
            continue
        typed: str = f'{match.ref.kind.value}("{match.ref.name}")'
        written: str = ".".join(
            part for part in (relation.database, relation.schema, relation.name) if part
        )
        raise CompileInputError(
            f"{owner.label} names {match.ref.kind.value}:{match.ref.name} as '{written}' in SQL "
            f"passed to ctx.{literal.method}()\n  --> {owner.relative_path.as_posix()}:"
            f"{literal.line}",
            code=HARD_CODED_PROJECT_RELATION_CODE,
            help=(
                f"{owner.declare_help.format(typed=typed)} and use ctx.relation({typed}) instead "
                "of the relation name\n"
                "  = help: while migrating a project, allow hard-coded relation names with "
                "[references] enforce_explicit = false in sqlbuild_project.toml"
            ),
        )
    return temporary
