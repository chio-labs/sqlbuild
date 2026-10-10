from __future__ import annotations

from dataclasses import dataclass

from tests.integration.src.sqlbuild.compiler.sql_test_glue.helpers import SqlTestCorpusShape


@dataclass(frozen=True)
class GeneratedSqlTestAssemblyParityTestCase:
    """Seeded SQL-test projects native and Python assembly must compile identically."""

    description: str
    seed: int
    count: int
    test_count: int
    shape: SqlTestCorpusShape
    expected_native_assemblies: dict[str, int]
