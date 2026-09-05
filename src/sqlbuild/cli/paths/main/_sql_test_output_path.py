"""SQL test artifact path entrypoint."""

from pathlib import Path

from sqlbuild.cli.paths._helpers.artifact_path import build_sql_test_output_path
from sqlbuild.compiler.planner.models import SqlTestPlanEntry


def sql_test_output_path(entry: SqlTestPlanEntry) -> Path:
    """Return the filesystem-safe target path for one SQL test artifact."""

    return build_sql_test_output_path(entry)
