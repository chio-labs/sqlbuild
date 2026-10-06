"""Generated projects are deterministic per seed and cover the intended feature space."""

from __future__ import annotations

import pytest

from scripts.compiler_differential.main.generate_project import generate_project
from scripts.compiler_differential.models import GeneratedProject
from tests.unit.scripts.compiler_differential.main._test_types import (
    SeedDeterminismTestCase,
    SeedRangeTestCase,
)
from tests.unit.scripts.compiler_differential.main.helpers import (
    generated_projects,
    invalid_count,
    project_features,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SeedDeterminismTestCase(description=f"seed_{seed}", seed=seed, expected_identical=True)
        for seed in (0, 7, 41)
    ],
    ids=lambda case: case.description,
)
def test_given_same_seed_when_generating_twice_then_projects_are_identical(
    test_case: SeedDeterminismTestCase,
) -> None:
    first: GeneratedProject = generate_project(seed=test_case.seed)
    second: GeneratedProject = generate_project(seed=test_case.seed)

    assert (first == second) is test_case.expected_identical


@pytest.mark.parametrize(
    "test_case",
    [
        SeedRangeTestCase(
            description="first_sixty_seeds",
            seeds=range(60),
            expected_features=frozenset(
                {
                    "exact_owner_scope",
                    "tree_scope",
                    "project_scope",
                    "model_private_value",
                    "relationship_grant",
                    "name_shared_across_namespaces",
                    "non_ascii_constant",
                    "float_constant",
                    "decimal_constant",
                    "integer_enum",
                    "macro_reads_ctx",
                    "macro_reads_env",
                    "nested_macro",
                    "path_defaults_literal",
                    "path_defaults_wildcard",
                    "sql_hooks",
                    "python_nodes",
                    "unit_test",
                    "scenario",
                    "singular_audit",
                    "column_audits",
                }
            ),
            expected_distinct_projects=60,
            expected_min_invalid=5,
            expected_max_invalid=30,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_seed_range_when_generating_then_features_and_failures_are_covered(
    test_case: SeedRangeTestCase,
) -> None:
    projects: list[GeneratedProject] = generated_projects(test_case.seeds)

    assert test_case.expected_features <= project_features(projects)
    assert len({tuple(project.files.items()) for project in projects}) == (
        test_case.expected_distinct_projects
    )
    assert (
        test_case.expected_min_invalid <= invalid_count(projects) <= test_case.expected_max_invalid
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
