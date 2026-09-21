"""Compiled SQL test artifact path entrypoint."""

from pathlib import Path

from sqlbuild.cli.paths._helpers.artifact_path import build_sql_test_output_path_from_values
from sqlbuild.compiler.compile.models import CompiledSqlTest


def compiled_sql_test_output_path(*, test: CompiledSqlTest, model_names: tuple[str, ...]) -> Path:
    """Return a test path from a compiled test and compact native plan facts."""

    return build_sql_test_output_path_from_values(
        name=test.name,
        source_path=test.source_path,
        block_index=test.block_index,
        case_name=test.case_name,
        model_names=model_names,
    )
