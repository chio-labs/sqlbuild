"""Typed reference arguments and explicit-reference enforcement for macro expansion."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from sqlbuild.compiler.compile._helpers.refs.references import extract_sql_references
from sqlbuild.compiler.compile.constants import MACRO_GENERATED_REFERENCE_CODE
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import CompileSqlReference, LoadedMacro
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.compiler.scopes.models import DeclarationIdentity, ResourceIdentity
from sqlbuild.compiler.scopes.types import ResourceKind
from sqlbuild.python_nodes.models import SqlResourceRef
from sqlbuild.python_nodes.types import SqlResourceRefKind

_TYPED_REFERENCE_KINDS: dict[str, SqlResourceRefKind] = {
    "__ref": SqlResourceRefKind.MODEL,
    "__source": SqlResourceRefKind.SOURCE,
    "__seed": SqlResourceRefKind.SEED,
}
_REFERENCE_FUNCTION_BY_KIND: dict[SqlResourceRefKind, str] = {
    kind: function for function, kind in _TYPED_REFERENCE_KINDS.items()
}
_EXPLICIT_REFERENCE_KINDS: dict[str, SqlResourceRefKind] = {
    SqlReferenceKind.REF.value: SqlResourceRefKind.MODEL,
    SqlReferenceKind.SOURCE.value: SqlResourceRefKind.SOURCE,
    SqlReferenceKind.SEED.value: SqlResourceRefKind.SEED,
}
_REFERENCE_CALL_MARKERS: tuple[str, ...] = tuple(f"{name}(" for name in _TYPED_REFERENCE_KINDS)
_RELATION_PLACEHOLDER_PREFIX: str = "__sqlbuild_relation_"
_RELATION_PLACEHOLDER_PATTERN: re.Pattern[str] = re.compile(
    rf"{_RELATION_PLACEHOLDER_PREFIX}(\d+)__"
)


def relation_placeholder_text(index: int) -> str:
    """Return the in-expansion placeholder text for the typed reference at ``index``."""

    return f"{_RELATION_PLACEHOLDER_PREFIX}{index}__"


def render_relation_placeholders(*, sql: str, relations: dict[SqlResourceRef, int]) -> str:
    """Replace placeholders with the reference call written at the macro call site."""

    if not relations or _RELATION_PLACEHOLDER_PREFIX not in sql:
        return sql
    ordered: tuple[SqlResourceRef, ...] = tuple(relations)
    return _RELATION_PLACEHOLDER_PATTERN.sub(
        lambda match: _reference_call_text(ordered[int(match.group(1))]), sql
    )


def _reference_call_text(ref: SqlResourceRef) -> str:
    return f'{_REFERENCE_FUNCTION_BY_KIND[ref.kind]}("{ref.name}")'


def reject_macro_generated_references(
    *,
    loaded_macro: LoadedMacro,
    macro_result: str,
    file_path: Path,
    consumer: ResourceIdentity | DeclarationIdentity | None,
) -> None:
    if not any(marker in macro_result for marker in _REFERENCE_CALL_MARKERS):
        return
    generated: SqlResourceRef | None = _first_generated_reference(macro_result)
    if generated is None:
        return
    consumer_label: str = (
        f"{consumer.kind.value}:{consumer.name}" if consumer is not None else f"'{file_path}'"
    )
    location: str = (
        "the model"
        if isinstance(consumer, ResourceIdentity) and consumer.kind is ResourceKind.MODEL
        else "the calling SQL"
    )
    raise CompileInputError(
        f"{consumer_label} depends on {generated.kind.value}:{generated.name} through macro "
        f"{loaded_macro.name}()\n  --> {loaded_macro.relative_path.as_posix()}",
        code=MACRO_GENERATED_REFERENCE_CODE,
        help=(
            f"write the reference in {location}, or pass it in: "
            f"@{loaded_macro.name}({_reference_call_text(generated)})\n"
            "  = help: while migrating a project, allow macro-generated references with "
            "[references] enforce_explicit = false in sqlbuild_project.toml"
        ),
    )


def _first_generated_reference(sql: str) -> SqlResourceRef | None:
    try:
        references: tuple[CompileSqlReference, ...] = extract_sql_references(sql)
    except CompileInputError:
        return None
    for reference in references:
        kind: SqlResourceRefKind | None = _EXPLICIT_REFERENCE_KINDS.get(str(reference.ref_kind))
        if kind is not None:
            return SqlResourceRef(kind=kind, name=reference.ref_name)
    return None


def evaluate_typed_reference(*, node: ast.Call, file_path: Path) -> SqlResourceRef:
    function_name: str | None = node.func.id if isinstance(node.func, ast.Name) else None
    kind: SqlResourceRefKind | None = (
        _TYPED_REFERENCE_KINDS.get(function_name) if function_name is not None else None
    )
    if kind is None:
        raise CompileInputError(
            f"Macro arguments in '{file_path}' must use only Python literals, nested macro "
            "calls, and __ref(), __source(), or __seed() references"
        )
    if (
        node.keywords
        or len(node.args) != 1
        or not isinstance(node.args[0], ast.Constant)
        or not isinstance(node.args[0].value, str)
        or not node.args[0].value
    ):
        raise CompileInputError(
            f"Macro argument {function_name}() in '{file_path}' must contain exactly one "
            "quoted resource name"
        )
    return SqlResourceRef(kind=kind, name=node.args[0].value)
