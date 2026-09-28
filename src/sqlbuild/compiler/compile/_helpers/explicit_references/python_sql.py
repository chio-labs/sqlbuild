"""Compile-time rejection of project relation names hard-coded in Python SQL."""

from __future__ import annotations

import ast
import inspect
import textwrap
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from sqlbuild.compiler.compile.constants import HARD_CODED_PROJECT_RELATION_CODE
from sqlbuild.compiler.compile.models import (
    CompiledProject,
    CompilerDiagnostic,
    PythonSqlReferenceReport,
)
from sqlbuild.compiler.compile.types import DiagnosticPhase, DiagnosticSeverity
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.graph.main._model_python_hook_names import model_python_hook_names
from sqlbuild.compiler.references.main._compiled_project_relations import (
    compiled_project_relations,
)
from sqlbuild.compiler.references.main._old_name_reference_message import (
    old_name_reference_message,
)
from sqlbuild.compiler.references.main.extract_relation_names import extract_relation_names
from sqlbuild.compiler.references.main.hard_coded_relation_remedy import (
    hard_coded_relation_remedy,
)
from sqlbuild.compiler.references.main.match_project_relation import match_project_relation
from sqlbuild.compiler.references.models import (
    LiteralSqlRelation,
    ProjectRelation,
    ProjectRelationIndex,
    RelationName,
)
from sqlbuild.compiler.references.types import HardCodedRelationOwnerKind
from sqlbuild.python_nodes.main.read_loader_definition import read_loader_definition
from sqlbuild.python_nodes.models import LoaderDefinition, SqlResourceRef
from sqlbuild.python_nodes.types import SqlResourceRefKind
from sqlbuild.spec.contracts.models import SourceLocation

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


def python_sql_reference_diagnostics(
    *, project: CompiledProject, discovered_inputs: DiscoveredProjectInputs
) -> PythonSqlReferenceReport:
    """Return P008 errors for project relations literal SQL in Python code names."""

    owners: tuple[_PythonSqlOwner, ...] = _owners(
        project=project, discovered_inputs=discovered_inputs
    )
    if not owners:
        return PythonSqlReferenceReport()
    index: ProjectRelationIndex = compiled_project_relations(
        project=project,
        old_name_retention=discovered_inputs.project_config.migrations.old_name_views,
    )
    diagnostics: dict[tuple[str, int, str, str], CompilerDiagnostic] = {}
    unmatched: list[LiteralSqlRelation] = []
    for owner in owners:
        temporary: frozenset[str] = frozenset()
        for literal in sorted(_literal_sql_calls(owner.function), key=lambda item: item.line):
            found: dict[tuple[str, int, str, str], CompilerDiagnostic]
            unnamed: tuple[LiteralSqlRelation, ...]
            temporary, found, unnamed = _hard_coded_relations(
                owner=owner,
                literal=literal,
                index=index,
                dialect=project.sql_analysis_dialect,
                temporary=temporary,
            )
            unmatched.extend(unnamed)
            for key, diagnostic in found.items():
                diagnostics.setdefault(key, diagnostic)
    return PythonSqlReferenceReport(
        diagnostics=tuple(
            diagnostics[key]
            for key in sorted(
                diagnostics,
                key=lambda key: (diagnostics[key].path or Path(), key[1], key[0], key[2], key[3]),
            )
        ),
        unmatched=tuple(dict.fromkeys(unmatched)),
    )


def _owners(
    *, project: CompiledProject, discovered_inputs: DiscoveredProjectInputs
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
    *, project: CompiledProject, discovered_inputs: DiscoveredProjectInputs
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


def _hard_coded_relations(
    *,
    owner: _PythonSqlOwner,
    literal: _LiteralSql,
    index: ProjectRelationIndex,
    dialect: str | None,
    temporary: frozenset[str],
) -> tuple[
    frozenset[str],
    dict[tuple[str, int, str, str], CompilerDiagnostic],
    tuple[LiteralSqlRelation, ...],
]:
    extracted: tuple[tuple[RelationName, ...], frozenset[str]] | None = extract_relation_names(
        sql=literal.sql, dialect=dialect
    )
    found: dict[tuple[str, int, str, str], CompilerDiagnostic] = {}
    unmatched: list[LiteralSqlRelation] = []
    if extracted is None:
        return temporary, found, ()
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
        if match is None:
            unmatched.append(
                LiteralSqlRelation(
                    owner_label=owner.label,
                    owner_kind=owner.kind,
                    relative_path=owner.relative_path,
                    line=literal.line,
                    method=literal.method,
                    relation=relation,
                )
            )
            continue
        if match.ref in owner.own_refs and match.compatibility_for is None:
            continue
        key: tuple[str, int, str, str] = (
            owner.label,
            literal.line,
            match.ref.kind.value,
            match.ref.name,
        )
        found.setdefault(
            key,
            _hard_coded_relation_diagnostic(
                owner=owner, literal=literal, relation=relation, match=match
            ),
        )
    return temporary, found, tuple(unmatched)


def _hard_coded_relation_diagnostic(
    *,
    owner: _PythonSqlOwner,
    literal: _LiteralSql,
    relation: RelationName,
    match: ProjectRelation,
) -> CompilerDiagnostic:
    written: str = ".".join(
        part for part in (relation.database, relation.schema, relation.name) if part
    )
    remedy: str = hard_coded_relation_remedy(
        owner_kind=owner.kind,
        ref=match.ref,
        upstream_loader_by_source=owner.upstream_loader_by_source,
    )
    qualify_help: str = (
        f"\n  = help: if '{written}' is an external table that shares the name, qualify it "
        "with its schema"
        if relation.schema is None
        else ""
    )
    return CompilerDiagnostic(
        phase=DiagnosticPhase.COMPILE,
        severity=DiagnosticSeverity.ERROR,
        code=HARD_CODED_PROJECT_RELATION_CODE,
        message=(
            old_name_reference_message(
                owner_label=owner.label,
                written=written,
                method=literal.method,
                model_name=match.compatibility_for,
            )
            if match.compatibility_for is not None
            else f"{owner.label} names {match.ref.kind.value}:{match.ref.name} as '{written}' "
            f"in SQL passed to ctx.{literal.method}()"
        ),
        location=SourceLocation(path=owner.relative_path, line=literal.line, column=1),
        help=(
            f"{remedy}{qualify_help}\n"
            "  = help: while migrating a project, allow hard-coded relation names with "
            "[references] enforce_explicit = false in sqlbuild_project.toml"
        ),
    )
