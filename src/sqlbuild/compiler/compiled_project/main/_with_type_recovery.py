"""Record a compiled model's semantic type recovery."""

from sqlbuild.compiler.compile.models import CompilerDiagnostic
from sqlbuild.compiler.compile.types import CompiledModelView
from sqlbuild.compiler.compiled_project._helpers.model_updates import with_type_recovery_impl


def with_type_recovery(
    *,
    model: CompiledModelView,
    diagnostics: tuple[CompilerDiagnostic, ...],
    poisoned: frozenset[tuple[str, str]],
) -> CompiledModelView:
    """The model with its recovered bindings and its poisoned outputs' types forgotten."""

    return with_type_recovery_impl(model=model, diagnostics=diagnostics, poisoned=poisoned)
