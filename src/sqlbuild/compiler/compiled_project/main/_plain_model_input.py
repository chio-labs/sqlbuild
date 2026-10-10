"""The Python model input for a model the native model loop finished."""

from sqlbuild.compiler.compile.models import CompileModelInput, SqlInterpolation
from sqlbuild.compiler.compiled_project._helpers.views import plain_model_input_impl
from sqlbuild.compiler.compiled_project.models import PlainModelFacts
from sqlbuild.compiler.discovery.models import (
    ConstantDeclaration,
    DiscoveredSqlModelFile,
    EnumDeclaration,
)


def plain_model_input(
    *,
    model_file: DiscoveredSqlModelFile,
    interpolation: SqlInterpolation,
    facts: PlainModelFacts,
    declarations: tuple[dict[str, EnumDeclaration], dict[str, ConstantDeclaration]],
) -> tuple[CompileModelInput, tuple[list[tuple[object, ...]], list[tuple[object, ...]]]]:
    """Return the model input the attachment would build and its local declaration rows."""

    return plain_model_input_impl(
        model_file=model_file, interpolation=interpolation, facts=facts, declarations=declarations
    )
