"""Public planner entrypoint for SQL-test model closure discovery."""

from sqlbuild.compiler.compile.models import CompiledModel, CompiledProject, CompiledSqlTest
from sqlbuild.compiler.planner._helpers.sql_tests.assembly import resolve_test_model_chain_names


def sql_test_model_chain_names(
    *,
    test: CompiledSqlTest,
    project: CompiledProject,
    model_map: dict[str, CompiledModel] | None = None,
) -> tuple[str, ...]:
    """Return the exact model closure a SQL test plan will expand."""

    return resolve_test_model_chain_names(test=test, project=project, model_map=model_map)
