"""Every corpus entry declares the outcome both engines must produce."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.compiler_differential._helpers.corpus.corpus import build_corpus
from scripts.compiler_differential.constants import COLD_COMPILE
from scripts.compiler_differential.models import CorpusProject, ExpectedOutcome
from tests.unit.scripts.compiler_differential._helpers.corpus._test_types import (
    CorpusExpectationTestCase,
    DialectVariantTestCase,
)

_REPO_ROOT: Path = Path(__file__).resolve().parents[6]


@pytest.mark.parametrize(
    "test_case",
    [
        CorpusExpectationTestCase(
            description="fixtures_succeed_except_dbt_interop",
            corpora=("fixtures",),
            expected_outcomes={
                "fixture/waffle_shop": ExpectedOutcome(),
                "fixture/dbt_interop": ExpectedOutcome(error_code="C214"),
            },
        ),
        CorpusExpectationTestCase(
            description="examples_succeed",
            corpora=("examples",),
            expected_outcomes={"example/waffle-shop": ExpectedOutcome()},
        ),
        CorpusExpectationTestCase(
            description="dense_succeeds",
            corpora=("dense",),
            expected_outcomes={
                "dense/20": ExpectedOutcome(),
                "dense/20-custom-rules": ExpectedOutcome(),
            },
        ),
        CorpusExpectationTestCase(
            description="extra_projects_take_the_declared_expectation",
            corpora=(),
            expected_outcomes={"project/orders": ExpectedOutcome(error_code="P001")},
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_corpus_selection_when_building_then_entries_declare_expected_outcomes(
    test_case: CorpusExpectationTestCase,
) -> None:
    corpus: list[CorpusProject] = build_corpus(
        repo_root=_REPO_ROOT,
        corpora=test_case.corpora,
        seeds=range(0),
        dense_models=20,
        projects=(Path("/projects/orders"),),
        project_expectation=ExpectedOutcome(error_code="P001"),
    )
    outcomes: dict[str, ExpectedOutcome] = {entry.name: entry.expected for entry in corpus}

    assert {
        name: outcomes.get(name) for name in test_case.expected_outcomes
    } == test_case.expected_outcomes


@pytest.mark.parametrize(
    "test_case",
    [
        DialectVariantTestCase(
            description="first_seed_compiles_under_each_dialect",
            seeds=range(5, 7),
            expected_names=(
                "seed/5",
                "seed/6",
                "seed/5-postgres",
                "seed/5-snowflake",
            ),
            expected_variant_commands=(COLD_COMPILE,),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_seed_range_when_building_then_first_seed_adds_compile_only_dialect_variants(
    test_case: DialectVariantTestCase,
) -> None:
    corpus: list[CorpusProject] = build_corpus(
        repo_root=_REPO_ROOT,
        corpora=("seeds",),
        seeds=test_case.seeds,
        dense_models=20,
        projects=(),
        project_expectation=ExpectedOutcome(),
    )
    variants: list[CorpusProject] = corpus[len(test_case.seeds) :]

    assert tuple(entry.name for entry in corpus) == test_case.expected_names
    assert all(entry.seed_coverage for entry in corpus)
    assert {entry.commands for entry in variants} == {test_case.expected_variant_commands}
    assert all(entry.expected == ExpectedOutcome() for entry in variants)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
