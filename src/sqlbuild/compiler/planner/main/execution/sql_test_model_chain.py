"""Public planner entrypoint for batched SQL-test model closure discovery."""

from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledProject, CompiledSqlTest
from sqlbuild.compiler.planner._helpers.sql_tests.native_planning import (
    resolve_sql_test_model_chains,
)


def sql_test_model_chain_names_by_key(
    *, project: CompiledProject, tests: tuple[CompiledSqlTest, ...]
) -> dict[CompiledObjectKey, tuple[str, ...]]:
    """Return model closures resolved natively in one project batch."""

    return {
        test.key: chain
        for test, chain in zip(
            tests, resolve_sql_test_model_chains(project=project, tests=tests), strict=True
        )
    }
