"""Strict kata configuration behavior tests."""

from pathlib import Path

import pytest

from sqlbuild.kata_engine.exceptions import KataError
from sqlbuild.kata_engine.main.load_config import load_kata_config
from sqlbuild.kata_engine.models import KataConfig, LayoutConfig, SqlTestPolicyConfig
from tests.unit.src.sqlbuild.kata_engine._helpers.engine._test_types import (
    KataConfigErrorTestCase,
    KataLayoutConfigTestCase,
    SqlTestPolicyConfigTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (
        KataConfigErrorTestCase(
            description="empty layout levels",
            source="[kata.layout]\nlevels = []\n",
            expected_error_pattern="kata.layout.levels must contain at least one",
        ),
        KataConfigErrorTestCase(
            description="traversing layout level",
            source='[kata.layout]\nlevels = ["../staging"]\n',
            expected_error_pattern="must be normalized project-relative paths",
        ),
        KataConfigErrorTestCase(
            description="duplicate layout level",
            source='[kata.layout]\nlevels = ["staging", "staging"]\n',
            expected_error_pattern="duplicate kata layout level: staging",
        ),
        KataConfigErrorTestCase(
            description="overlapping layout levels",
            source=('[kata.layout]\nlevels = ["intermediate", "intermediate/enriched"]\n'),
            expected_error_pattern="kata.layout.levels entries must not overlap",
        ),
        KataConfigErrorTestCase(
            description="overlapping explicit domain roots",
            source=('[kata.layout]\ndomain_roots = ["market", "market/betfair"]\n'),
            expected_error_pattern="kata.layout.domain_roots entries must not overlap",
        ),
        KataConfigErrorTestCase(
            description="unknown top-level key",
            source='[kata]\nselect = ["SQBKS"]\nseverity = "warn"\n',
            expected_error_pattern="unknown kata config keys: severity",
        ),
        KataConfigErrorTestCase(
            description="unknown threshold",
            source="[kata.thresholds]\nmax_models = 3\n",
            expected_error_pattern="unknown kata thresholds: max_models",
        ),
        KataConfigErrorTestCase(
            description="reasonless ignore",
            source=('[[kata.rule_ignores]]\nrules = ["SQBKS"]\npaths = ["models/**"]\n'),
            expected_error_pattern="kata.rule_ignores.reason",
        ),
        KataConfigErrorTestCase(
            description="reasonless threshold override",
            source=(
                '[[kata.threshold_overrides]]\npaths = ["models/mart/**"]\n'
                "thresholds = { min_tests_per_model = 2 }\n"
            ),
            expected_error_pattern="kata.threshold_overrides.reason",
        ),
        KataConfigErrorTestCase(
            description="unknown scoped threshold",
            source=(
                '[[kata.threshold_overrides]]\npaths = ["models/mart/**"]\n'
                'reason = "marts need stronger coverage"\n'
                "thresholds = { max_models = 2 }\n"
            ),
            expected_error_pattern="unknown kata threshold override: max_models",
        ),
        KataConfigErrorTestCase(
            description="project-wide threshold used as path override",
            source=(
                '[[kata.threshold_overrides]]\npaths = ["models/mart/**"]\n'
                'reason = "custom rule evidence is project-wide"\n'
                "thresholds = { min_custom_rule_test_cases = 2 }\n"
            ),
            expected_error_pattern=("unknown kata threshold override: min_custom_rule_test_cases"),
        ),
        KataConfigErrorTestCase(
            description="invalid threshold override glob",
            source=(
                '[[kata.threshold_overrides]]\npaths = ["models/["]\n'
                'reason = "invalid migration pattern"\n'
                "thresholds = { min_tests_per_model = 2 }\n"
            ),
            expected_error_pattern="invalid kata threshold override path",
        ),
        KataConfigErrorTestCase(
            description="empty threshold override glob",
            source=(
                '[[kata.threshold_overrides]]\npaths = [""]\n'
                'reason = "empty migration pattern"\n'
                "thresholds = { min_tests_per_model = 2 }\n"
            ),
            expected_error_pattern="threshold override paths must be non-empty globs",
        ),
        KataConfigErrorTestCase(
            description="transitional rule namespace",
            source='[kata]\nselect = ["KTS"]\n',
            expected_error_pattern="malformed kata rule selector: KTS",
        ),
        KataConfigErrorTestCase(
            description="absolute pipeline directory",
            source='[kata.sql_tests]\npipeline_directory = "/pipelines"\n',
            expected_error_pattern="must be a normalized path relative to tests/unit",
        ),
        KataConfigErrorTestCase(
            description="traversing pipeline directory",
            source='[kata.sql_tests]\npipeline_directory = "../pipelines"\n',
            expected_error_pattern="must be a normalized path relative to tests/unit",
        ),
        KataConfigErrorTestCase(
            description="unnormalized pipeline directory",
            source='[kata.sql_tests]\npipeline_directory = "chains//commerce"\n',
            expected_error_pattern="must be a normalized path relative to tests/unit",
        ),
        KataConfigErrorTestCase(
            description="unknown SQL test policy key",
            source='[kata.sql_tests]\npipeline_directory = "pipelines"\nroot = "tests"\n',
            expected_error_pattern="unknown field `root`",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_invalid_kata_config_when_loading_then_raises_clear_error(
    tmp_path: Path,
    test_case: KataConfigErrorTestCase,
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(test_case.source, encoding="utf-8")

    with pytest.raises(KataError, match=test_case.expected_error_pattern):
        load_kata_config(project_dir=tmp_path)


@pytest.mark.parametrize(
    "test_case",
    (
        SqlTestPolicyConfigTestCase(
            description="nested pipeline directory",
            source='[kata.sql_tests]\npipeline_directory = "chains/commerce"\n',
            expected_pipeline_directory="chains/commerce",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_pipeline_directory_when_loading_then_returns_typed_relative_configuration(
    tmp_path: Path,
    test_case: SqlTestPolicyConfigTestCase,
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(test_case.source, encoding="utf-8")

    config: KataConfig = load_kata_config(project_dir=tmp_path)

    assert config.sql_tests == SqlTestPolicyConfig(
        pipeline_directory=test_case.expected_pipeline_directory
    )


@pytest.mark.parametrize(
    "test_case",
    (
        KataLayoutConfigTestCase(
            description="custom levels and thresholds",
            source=(
                '[kata.layout]\nlevels = ["raw", "conformed/clean", "reporting"]\n'
                'domain_roots = ["market/betfair", "model/horsenet/ratings"]\n'
                "[kata.thresholds]\n"
                "max_subdomain_depth = 2\n"
                "min_shared_owner_prefix_directories = 2\n"
                "max_role_container_depth = 1\n"
                "max_macro_container_files = 12\n"
                "max_constant_container_files = 8\n"
                "max_enum_container_files = 6\n"
                "min_shared_container_prefix_files = 2\n"
            ),
            expected_levels=("raw", "conformed/clean", "reporting"),
            expected_thresholds={
                "max_subdomain_depth": 2,
                "min_shared_owner_prefix_directories": 2,
                "max_role_container_depth": 1,
                "max_macro_container_files": 12,
                "max_constant_container_files": 8,
                "max_enum_container_files": 6,
                "min_shared_container_prefix_files": 2,
            },
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_layout_and_thresholds_when_loading_then_returns_typed_configuration(
    test_case: KataLayoutConfigTestCase,
    tmp_path: Path,
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        test_case.source,
        encoding="utf-8",
    )

    config: KataConfig = load_kata_config(project_dir=tmp_path)

    assert config.layout == LayoutConfig(
        levels=test_case.expected_levels,
        domain_roots=("market/betfair", "model/horsenet/ratings"),
    )
    assert config.thresholds == test_case.expected_thresholds
