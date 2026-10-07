"""Typed reference arguments and explicit-reference enforcement for macro expansion."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from sqlbuild.compiler.compile._helpers.diagnostics.collector import (
    report_compile_diagnostic,
)
from sqlbuild.compiler.compile._helpers.refs.references import (
    extract_sql_references,
    reference_call_location,
    reference_call_syntax_key,
    scan_sql_reference_calls,
)
from sqlbuild.compiler.compile.constants import (
    MACRO_GENERATED_REFERENCE_CODE,
    REFERENCE_CALL_SYNTAX_CODE,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import (
    CompilerDiagnostic,
    CompileSqlReference,
    InvalidSqlReferenceCall,
    LoadedMacro,
)
from sqlbuild.compiler.compile.types import (
    CompiledResourceType,
    DiagnosticPhase,
    DiagnosticSeverity,
)
from sqlbuild.compiler.discovery.main.explicit_references_help import explicit_references_help
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.compiler.scopes.models import DeclarationIdentity, ResourceIdentity
from sqlbuild.compiler.scopes.types import ResourceKind
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax
from sqlbuild.python_nodes.models import SqlResourceRef
from sqlbuild.python_nodes.types import SqlResourceRefKind
from sqlbuild.spec.contracts.models import SourceLocation

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
_RESOURCE_TYPE_BY_CONSUMER_KIND: dict[ResourceKind, CompiledResourceType] = {
    ResourceKind.MODEL: CompiledResourceType.MODEL,
    ResourceKind.SOURCE: CompiledResourceType.SOURCE,
    ResourceKind.SEED: CompiledResourceType.SEED,
}
_REFERENCE_CALL_MARKERS: tuple[str, ...] = tuple(f"{name}(" for name in _TYPED_REFERENCE_KINDS)
_ALL_REFERENCE_CALL_MARKERS: tuple[str, ...] = tuple(
    f"{kind.function_name}(" for kind in SqlReferenceKind
)
_PASSABLE_REFERENCE_KINDS: frozenset[SqlReferenceKind] = frozenset(
    {SqlReferenceKind.REF, SqlReferenceKind.SOURCE, SqlReferenceKind.SEED}
)
_RELATION_PLACEHOLDER_PREFIX: str = "__sqlbuild_relation_"
_RELATION_PLACEHOLDER_PATTERN: re.Pattern[str] = re.compile(
    rf"{_RELATION_PLACEHOLDER_PREFIX}(\d+)__"
)

_GENERIC_SQL_SYNTAX: SqlLexicalSyntax = SqlLexicalSyntax()


def relation_placeholder_text(index: int) -> str:
    """Return the in-expansion placeholder text for the typed reference at ``index``."""

    return f"{_RELATION_PLACEHOLDER_PREFIX}{index}__"


def render_relation_placeholders(*, sql: str, relations: dict[SqlResourceRef, int]) -> str:
    """Replace placeholders with the reference call written at the macro call site."""

    if not relations or _RELATION_PLACEHOLDER_PREFIX not in sql:
        return sql
    ordered: tuple[SqlResourceRef, ...] = tuple(relations)
    return _RELATION_PLACEHOLDER_PATTERN.sub(
        lambda match: reference_call_text(ordered[int(match.group(1))]), sql
    )


def reference_call_text(ref: SqlResourceRef) -> str:
    """Return the SQL reference call that names ``ref``, such as ``__ref("orders")``."""

    return f'{_REFERENCE_FUNCTION_BY_KIND[ref.kind]}("{ref.name}")'


def call_site_sql_references(
    refs: tuple[SqlResourceRef, ...],
) -> tuple[CompileSqlReference, ...]:
    """Return the SQL references written as typed macro arguments, as SQL extraction sees them."""

    if not refs:
        return ()
    return extract_sql_references(
        sql=" ".join(reference_call_text(ref) for ref in refs), syntax=_GENERIC_SQL_SYNTAX
    )


def resource_references(
    references: tuple[CompileSqlReference, ...],
) -> tuple[SqlResourceRef, ...]:
    """Return the model, source, and seed references among SQL references, once each."""

    resources: dict[SqlResourceRef, None] = {}
    for reference in references:
        kind: SqlResourceRefKind | None = _EXPLICIT_REFERENCE_KINDS.get(str(reference.ref_kind))
        if kind is not None:
            resources[SqlResourceRef(kind=kind, name=reference.ref_name)] = None
    return tuple(resources)


def merge_call_site_references(
    *,
    references: tuple[CompileSqlReference, ...],
    argument_references: tuple[CompileSqlReference, ...],
) -> tuple[CompileSqlReference, ...]:
    """Add typed macro arguments to the references found in expanded SQL, once each."""

    if not argument_references:
        return references
    return tuple(dict.fromkeys((*references, *argument_references)))


def reject_macro_generated_references(
    *,
    loaded_macro: LoadedMacro,
    macro_result: str,
    file_path: Path,
    consumer: ResourceIdentity | DeclarationIdentity | None,
) -> None:
    """Report each typed reference a macro emitted instead of receiving it as an argument."""

    if not any(marker in macro_result for marker in _REFERENCE_CALL_MARKERS):
        return
    consumer_label: str = (
        f"{consumer.kind.value}:{consumer.name}" if consumer is not None else f"'{file_path}'"
    )
    location: str = (
        "the model"
        if isinstance(consumer, ResourceIdentity) and consumer.kind is ResourceKind.MODEL
        else "the calling SQL"
    )
    resource: ResourceIdentity | None = consumer if isinstance(consumer, ResourceIdentity) else None
    resource_type: CompiledResourceType | None = (
        _RESOURCE_TYPE_BY_CONSUMER_KIND.get(resource.kind) if resource is not None else None
    )
    generated: SqlResourceRef
    for generated in _generated_references(macro_result):
        report_compile_diagnostic(
            key=(
                MACRO_GENERATED_REFERENCE_CODE,
                consumer_label,
                loaded_macro.name,
                generated.kind.value,
                generated.name,
            ),
            diagnostic=CompilerDiagnostic(
                phase=DiagnosticPhase.COMPILE,
                severity=DiagnosticSeverity.ERROR,
                code=MACRO_GENERATED_REFERENCE_CODE,
                message=(
                    f"{consumer_label} depends on {generated.kind.value}:{generated.name} "
                    f"through macro {loaded_macro.name}()"
                ),
                resource_type=resource_type,
                resource_name=(
                    resource.name if resource is not None and resource_type is not None else None
                ),
                path=loaded_macro.relative_path,
                help=(
                    f"write the reference in {location}, or pass it in: "
                    f"@{loaded_macro.name}({reference_call_text(generated)})\n"
                    "  = help: " + explicit_references_help(allowed="macro-generated references")
                ),
            ),
        )


def report_macro_reference_call_syntax(
    *,
    loaded_macro: LoadedMacro,
    macro_result: str,
    file_path: Path,
    consumer: ResourceIdentity | DeclarationIdentity | None,
) -> None:
    """Report each reference call a macro returned that compile could not replace."""

    if not any(marker in macro_result for marker in _ALL_REFERENCE_CALL_MARKERS):
        return
    try:
        invalid_calls: tuple[InvalidSqlReferenceCall, ...] = scan_sql_reference_calls(
            sql=macro_result, syntax=_GENERIC_SQL_SYNTAX
        ).invalid_calls
    except CompileInputError:
        return
    resource: ResourceIdentity | None = consumer if isinstance(consumer, ResourceIdentity) else None
    resource_type: CompiledResourceType | None = (
        _RESOURCE_TYPE_BY_CONSUMER_KIND.get(resource.kind) if resource is not None else None
    )
    location: str = (
        "the model"
        if isinstance(consumer, ResourceIdentity) and consumer.kind is ResourceKind.MODEL
        else "the calling SQL"
    )
    for invalid_call in invalid_calls:
        pass_in_help: str = (
            f"write {invalid_call.corrected_call} in {location} and pass it in: "
            f"@{loaded_macro.name}({invalid_call.corrected_call})\n  = help: "
            if invalid_call.ref_kind in _PASSABLE_REFERENCE_KINDS
            else ""
        )
        report_compile_diagnostic(
            key=reference_call_syntax_key(
                file_path=file_path, call=invalid_call.call, location=None
            ),
            diagnostic=CompilerDiagnostic(
                phase=DiagnosticPhase.COMPILE,
                severity=DiagnosticSeverity.ERROR,
                code=REFERENCE_CALL_SYNTAX_CODE,
                message=f"{invalid_call.message}, returned by macro {loaded_macro.name}()",
                resource_type=resource_type,
                resource_name=(
                    resource.name if resource is not None and resource_type is not None else None
                ),
                path=loaded_macro.relative_path,
                location=_macro_source_location(loaded_macro=loaded_macro, call=invalid_call.call),
                help=f"{pass_in_help}{invalid_call.help}",
            ),
        )


def _macro_source_location(*, loaded_macro: LoadedMacro, call: str) -> SourceLocation | None:
    start: int = loaded_macro.raw_source.find(call)
    if start == -1:
        return None
    return reference_call_location(
        path=loaded_macro.relative_path, text=loaded_macro.raw_source, start=start, call=call
    )


def _generated_references(sql: str) -> tuple[SqlResourceRef, ...]:
    try:
        references: tuple[CompileSqlReference, ...] = scan_sql_reference_calls(
            sql=sql, syntax=_GENERIC_SQL_SYNTAX
        ).references
    except CompileInputError:
        return ()
    generated: dict[SqlResourceRef, None] = {}
    for reference in references:
        kind: SqlResourceRefKind | None = _EXPLICIT_REFERENCE_KINDS.get(str(reference.ref_kind))
        if kind is not None:
            generated[SqlResourceRef(kind=kind, name=reference.ref_name)] = None
    return tuple(generated)


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
