from __future__ import annotations

from dataclasses import dataclass

from tests.integration.src.sqlbuild.compiler.sql_test_glue.helpers import SqlTestCorpusShape


@dataclass(frozen=True)
class GeneratedSqlTestAssemblyParityTestCase:
    """Seeded SQL-test projects native assembly must compile as Python's recorded assembly did."""

    description: str
    seed: int
    count: int
    test_count: int
    shape: SqlTestCorpusShape
    expected_native_assemblies: dict[str, int]


@dataclass(frozen=True)
class EdgeSqlTestAssemblyTestCase:
    """One project whose SQL test Python's assembly once answered alone, and its outcome kind."""

    description: str
    files: dict[str, str]
    expected_outcome: str
