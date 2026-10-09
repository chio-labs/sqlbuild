from __future__ import annotations

from dataclasses import dataclass

from tests.integration.src.sqlbuild.compiler.sql_test_glue.helpers import SqlTestCorpusShape


@dataclass(frozen=True)
class GeneratedSqlTestPlanningParityTestCase:
    """Seeded SQL-test projects the native planning glue and the JSON request must agree on."""

    description: str
    seed: int
    count: int
    test_count: int
    shape: SqlTestCorpusShape
    adapter_names: tuple[str, ...]
    expected_minimum_native_planned: int
    expected_minimum_native_with_errors: int
    expected_minimum_native_chains: int
    expected_minimum_native_raised: int
    expected_native_raised_kinds: frozenset[str]
    expected_minimum_answered_batches: int
    expected_minimum_raised_outcomes: int


@dataclass(frozen=True)
class GeneratedSqlTestAssemblyParityTestCase:
    """Seeded SQL-test projects native and Python assembly must compile identically."""

    description: str
    seed: int
    count: int
    test_count: int
    shape: SqlTestCorpusShape
    expected_minimum_native_assembled: int
    expected_minimum_native_with_diagnostics: int
    expected_minimum_native_case_fingerprints: int
    expected_minimum_deferred_macro_mocks: int
