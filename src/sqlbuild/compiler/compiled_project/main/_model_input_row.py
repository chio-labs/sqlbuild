"""A model input as the row the native compiled project retains."""

from sqlbuild.compiler.compile.models import CompileModelInput
from sqlbuild.compiler.compiled_project._helpers.rows import model_input_row_impl


def model_input_row(model_input: CompileModelInput) -> tuple[object, ...]:
    """Return the model's identity, config, references, schema and declarations as one row."""

    return model_input_row_impl(model_input)
