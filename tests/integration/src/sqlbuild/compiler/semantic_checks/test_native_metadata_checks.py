"""Native semantic metadata checks equal Python's on generated projects, family by family."""

from __future__ import annotations

import random
from collections import Counter
from pathlib import Path

import pytest

from sqlbuild.compiler.compile.models import CompilerDiagnostic
from tests.integration.src.sqlbuild.compiler.semantic_checks._test_types import (
    GeneratedMetadataParityTestCase,
)
from tests.integration.src.sqlbuild.compiler.semantic_checks.helpers import (
    SemanticInputs,
    captured_semantic_inputs,
    generated_metadata_files,
    native_metadata,
    python_metadata,
    record_metadata_families,
    with_dialect,
)


@pytest.mark.parametrize(
    "test_case",
    [
        GeneratedMetadataParityTestCase(
            description="function calls, config references, cursors, audits and SQL tests",
            seed=20261010,
            count=8,
            model_count=10,
            dialects=("duckdb", "postgres", "snowflake", "bigquery"),
            expected_minimum_native=32,
            expected_minimum_families={
                "function B102": 100,
                "function B301": 100,
                "reference B300": 50,
                "reference B301": 16,
                "source B300": 4,
                "sql_test B302": 16,
            },
        )
    ],
    ids=lambda case: case.description,
)
def test_given_generated_projects_when_checking_metadata_natively_then_matches_python(
    test_case: GeneratedMetadataParityTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rng: random.Random = random.Random(test_case.seed)
    families: Counter[str] = record_metadata_families(monkeypatch=monkeypatch)
    expected: list[tuple[CompilerDiagnostic, ...] | None] = []
    actual: list[tuple[CompilerDiagnostic, ...] | None] = []
    for index in range(test_case.count):
        captured: SemanticInputs = captured_semantic_inputs(
            project_dir=tmp_path / f"project_{index}",
            files=generated_metadata_files(rng=rng, model_count=test_case.model_count),
            monkeypatch=monkeypatch,
        )
        for dialect in test_case.dialects:
            inputs: SemanticInputs = with_dialect(captured, dialect)
            expected.append(python_metadata(inputs=inputs))
            actual.append(native_metadata(inputs))

    assert actual == expected
    assert families["deferred"] == 0
    assert families["native"] >= test_case.expected_minimum_native
    assert {
        family: min(families[family], minimum)
        for family, minimum in test_case.expected_minimum_families.items()
    } == test_case.expected_minimum_families


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
