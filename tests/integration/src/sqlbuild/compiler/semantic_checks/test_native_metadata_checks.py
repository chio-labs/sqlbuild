"""Native semantic metadata checks match the outputs recorded from Python's checks."""

from __future__ import annotations

import random
from collections import Counter
from functools import partial
from pathlib import Path

import pytest

from tests.integration.src.sqlbuild.compiler.golden_views import (
    GoldenEntry,
    golden_differences,
    golden_entry,
    golden_name,
    read_golden,
)
from tests.integration.src.sqlbuild.compiler.semantic_checks._test_types import (
    GeneratedMetadataParityTestCase,
)
from tests.integration.src.sqlbuild.compiler.semantic_checks.helpers import (
    SemanticInputs,
    captured_semantic_inputs,
    generated_metadata_files,
    native_metadata,
    non_ascii_variant,
    record_metadata_families,
    semantic_outcome,
    with_dialect,
)


def metadata_files(*, rng: random.Random, model_count: int, non_ascii: bool) -> dict[str, str]:
    files: dict[str, str] = generated_metadata_files(rng=rng, model_count=model_count)
    return non_ascii_variant(files=files, rng=rng) if non_ascii else files


@pytest.mark.parametrize(
    "test_case",
    [
        GeneratedMetadataParityTestCase(
            description="function calls, config references, cursors, audits and SQL tests",
            seed=20261010,
            count=8,
            model_count=10,
            dialects=("duckdb", "postgres", "snowflake", "bigquery"),
            non_ascii=False,
            golden_prefix="metadata_generated",
            expected_minimum_native=32,
            expected_minimum_families={
                "function B102": 100,
                "function B301": 100,
                "reference B300": 50,
                "reference B301": 16,
                "source B300": 4,
                "sql_test B302": 16,
            },
        ),
        GeneratedMetadataParityTestCase(
            description="non-ASCII names and comments, new and unknown dialects",
            seed=20261017,
            count=4,
            model_count=10,
            dialects=("duckdb", "mysql", "tsql", None, "nonsense"),
            non_ascii=True,
            golden_prefix="metadata_formerly_deferred",
            expected_minimum_native=12,
            expected_minimum_families={"function B301": 10, "reference B300": 4},
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_generated_projects_when_checking_metadata_natively_then_matches_recorded_python(
    test_case: GeneratedMetadataParityTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rng: random.Random = random.Random(test_case.seed)
    families: Counter[str] = record_metadata_families(monkeypatch=monkeypatch)
    golden: list[GoldenEntry] = []
    for index in range(test_case.count):
        project_dir: Path = tmp_path / f"project_{index}"
        captured: SemanticInputs = captured_semantic_inputs(
            project_dir=project_dir,
            files=metadata_files(
                rng=rng, model_count=test_case.model_count, non_ascii=test_case.non_ascii
            ),
            monkeypatch=monkeypatch,
        )
        views: dict[str, object] = {
            str(dialect): semantic_outcome(
                partial(native_metadata, with_dialect(captured, dialect))
            )
            for dialect in test_case.dialects
        }
        golden.append(golden_entry("metadata", views, masked=(str(project_dir),)))

    assert (
        golden_differences(
            read_golden(golden_name(test_case.golden_prefix, test_case.description)), golden
        )
        == []
    )
    assert families["native"] >= test_case.expected_minimum_native
    assert {
        family: min(families[family], minimum)
        for family, minimum in test_case.expected_minimum_families.items()
    } == test_case.expected_minimum_families


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
