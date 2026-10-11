"""Record a compiled model's final binding diagnostics."""

from sqlbuild.compiler.compile.models import CompilerDiagnostic
from sqlbuild.compiler.compile.types import CompiledModelView
from sqlbuild.compiler.compiled_project._helpers.model_updates import with_binding_diagnostics_impl


def with_binding_diagnostics(
    *, model: CompiledModelView, diagnostics: tuple[CompilerDiagnostic, ...]
) -> CompiledModelView:
    """The model with these final binding diagnostics."""

    return with_binding_diagnostics_impl(model=model, diagnostics=diagnostics)
