"""Report declaration-scope index errors as individual compile diagnostics."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.compile._helpers.diagnostics.collector import report_compile_diagnostic
from sqlbuild.compiler.compile.models import CompilerDiagnostic
from sqlbuild.compiler.compile.types import (
    CompiledResourceType,
    DiagnosticPhase,
    DiagnosticSeverity,
)
from sqlbuild.compiler.scopes.models import ScopeDiagnostic, ScopeIndex
from sqlbuild.compiler.scopes.types import DeclarationKind, ResourceKind
from sqlbuild.compiler.scopes.types import DiagnosticSeverity as ScopeSeverity

_RESOURCE_TYPES: dict[ResourceKind, CompiledResourceType] = {
    ResourceKind.MODEL: CompiledResourceType.MODEL,
    ResourceKind.SOURCE: CompiledResourceType.SOURCE,
    ResourceKind.SEED: CompiledResourceType.SEED,
    ResourceKind.FUNCTION: CompiledResourceType.UDF,
    ResourceKind.TEST: CompiledResourceType.SQL_TEST,
    ResourceKind.SCENARIO: CompiledResourceType.SQL_SCENARIO,
}
_DECLARATION_RESOURCE_TYPES: dict[DeclarationKind, CompiledResourceType] = {
    DeclarationKind.AUDIT: CompiledResourceType.AUDIT,
    DeclarationKind.SINGULAR_AUDIT: CompiledResourceType.AUDIT,
}


def compiled_resource_type(kind: ResourceKind) -> CompiledResourceType | None:
    """Return the compiled resource type diagnostics use for a scope resource kind."""

    return _RESOURCE_TYPES.get(kind)


def report_scope_index_errors(*, index: ScopeIndex) -> None:
    """Report each error-severity scope finding as its own compile diagnostic."""

    for item in index.diagnostics:
        if item.severity is not ScopeSeverity.ERROR:
            continue
        report_compile_diagnostic(
            key=(
                item.code.value,
                item.path or "",
                str(item.declaration or ""),
                str(item.resource or ""),
                item.message,
            ),
            diagnostic=_compile_diagnostic(item),
        )


def _compile_diagnostic(item: ScopeDiagnostic) -> CompilerDiagnostic:
    resource_type: CompiledResourceType | None = None
    resource_name: str | None = None
    if item.resource is not None and item.resource.kind in _RESOURCE_TYPES:
        resource_type = _RESOURCE_TYPES[item.resource.kind]
        resource_name = item.resource.name
    elif item.declaration is not None and item.declaration.kind in _DECLARATION_RESOURCE_TYPES:
        resource_type = _DECLARATION_RESOURCE_TYPES[item.declaration.kind]
        resource_name = item.declaration.name
    return CompilerDiagnostic(
        phase=DiagnosticPhase.COMPILE,
        severity=DiagnosticSeverity.ERROR,
        code=item.code.value,
        message=item.message,
        resource_type=resource_type,
        resource_name=resource_name,
        path=Path(item.path) if item.path is not None else None,
        line=item.line,
        column=item.column,
    )
