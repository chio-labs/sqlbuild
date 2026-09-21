"""Public planner entrypoint for batched SQL-test model closure discovery."""

from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledProject, CompiledSqlTest
from sqlbuild.compiler.planner._helpers.sql_tests.assembly import build_sql_test_planning_context


def sql_test_model_chain_names_by_key(
    *, project: CompiledProject, tests: tuple[CompiledSqlTest, ...]
) -> dict[CompiledObjectKey, tuple[str, ...]]:
    """Return model closures using one shared project dependency index."""

    return build_sql_test_planning_context(
        project=project,
        tests=tests,
    ).chain_names_by_test_key
