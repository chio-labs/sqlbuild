"""Strict policy configuration behavior tests."""

from pathlib import Path

import pytest

from sqlbuild.policy_engine.exceptions import PolicyError
from sqlbuild.policy_engine.main.load_config import load_policy_config
from sqlbuild.policy_engine.models import LayoutConfig, PolicyConfig, SqlTestPolicyConfig
from tests.unit.src.sqlbuild.policy_engine._helpers.engine._test_types import (
    PolicyConfigErrorTestCase,
    PolicyLayoutConfigTestCase,
    SqlTestPolicyConfigTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (
        PolicyConfigErrorTestCase(
            description="empty layout levels",
            source="[policy.layout]\nlevels = []\n",
            expected_error_pattern="policy.layout.levels must contain at least one",
        ),
        PolicyConfigErrorTestCase(
            description="traversing layout level",
            source='[policy.layout]\nlevels = ["../staging"]\n',
            expected_error_pattern="must be normalized project-relative paths",
        ),
        PolicyConfigErrorTestCase(
            description="duplicate layout level",
            source='[policy.layout]\nlevels = ["staging", "staging"]\n',
            expected_error_pattern="duplicate policy layout level: staging",
        ),
        PolicyConfigErrorTestCase(
            description="overlapping layout levels",
            source=('[policy.layout]\nlevels = ["intermediate", "intermediate/enriched"]\n'),
            expected_error_pattern="policy.layout.levels entries must not overlap",
        ),
        PolicyConfigErrorTestCase(
            description="overlapping explicit domain roots",
            source=('[policy.layout]\ndomain_roots = ["sales", "sales/partner"]\n'),
            expected_error_pattern="policy.layout.domain_roots entries must not overlap",
        ),
        PolicyConfigErrorTestCase(
            description="unknown top-level key",
            source='[policy]\nselect = ["SQBPS"]\nseverity = "warn"\n',
            expected_error_pattern="unknown policy config keys: severity",
        ),
        PolicyConfigErrorTestCase(
            description="removed legacy policy section",
            source='[kata]\nselect = ["SQBK"]\n',
            expected_error_pattern=r"unsupported legacy \[kata\] configuration",
        ),
        PolicyConfigErrorTestCase(
            description="unknown threshold",
            source="[policy.thresholds]\nmax_models = 3\n",
            expected_error_pattern="unknown policy thresholds: max_models",
        ),
        PolicyConfigErrorTestCase(
            description="reasonless ignore",
            source=('[[policy.rule_ignores]]\nrules = ["SQBPS"]\npaths = ["models/**"]\n'),
            expected_error_pattern="policy.rule_ignores.reason",
        ),
        PolicyConfigErrorTestCase(
            description="reasonless threshold override",
            source=(
                '[[policy.threshold_overrides]]\npaths = ["models/mart/**"]\n'
                "thresholds = { min_tests_per_model = 2 }\n"
            ),
            expected_error_pattern="policy.threshold_overrides.reason",
        ),
        PolicyConfigErrorTestCase(
            description="unknown scoped threshold",
            source=(
                '[[policy.threshold_overrides]]\npaths = ["models/mart/**"]\n'
                'reason = "marts need stronger coverage"\n'
                "thresholds = { max_models = 2 }\n"
            ),
            expected_error_pattern="unknown policy threshold override: max_models",
        ),
        PolicyConfigErrorTestCase(
            description="project-wide threshold used as path override",
            source=(
                '[[policy.threshold_overrides]]\npaths = ["models/mart/**"]\n'
                'reason = "custom rule evidence is project-wide"\n'
                "thresholds = { min_custom_rule_test_cases = 2 }\n"
            ),
            expected_error_pattern=(
                "unknown policy threshold override: min_custom_rule_test_cases"
            ),
        ),
        PolicyConfigErrorTestCase(
            description="invalid threshold override glob",
            source=(
                '[[policy.threshold_overrides]]\npaths = ["models/["]\n'
                'reason = "invalid migration pattern"\n'
                "thresholds = { min_tests_per_model = 2 }\n"
            ),
            expected_error_pattern="invalid policy threshold override path",
        ),
        PolicyConfigErrorTestCase(
            description="empty threshold override glob",
            source=(
                '[[policy.threshold_overrides]]\npaths = [""]\n'
                'reason = "empty migration pattern"\n'
                "thresholds = { min_tests_per_model = 2 }\n"
            ),
            expected_error_pattern="threshold override paths must be non-empty globs",
        ),
        PolicyConfigErrorTestCase(
            description="transitional rule namespace",
            source='[policy]\nselect = ["KTS"]\n',
            expected_error_pattern="malformed policy rule selector: KTS",
        ),
        PolicyConfigErrorTestCase(
            description="absolute pipeline directory",
            source='[policy.sql_tests]\npipeline_directory = "/pipelines"\n',
            expected_error_pattern="must be a normalized path relative to tests/unit",
        ),
        PolicyConfigErrorTestCase(
            description="traversing pipeline directory",
            source='[policy.sql_tests]\npipeline_directory = "../pipelines"\n',
            expected_error_pattern="must be a normalized path relative to tests/unit",
        ),
        PolicyConfigErrorTestCase(
            description="unnormalized pipeline directory",
            source='[policy.sql_tests]\npipeline_directory = "chains//commerce"\n',
            expected_error_pattern="must be a normalized path relative to tests/unit",
        ),
        PolicyConfigErrorTestCase(
            description="unknown SQL test policy key",
            source='[policy.sql_tests]\npipeline_directory = "pipelines"\nroot = "tests"\n',
            expected_error_pattern="unknown field `root`",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_invalid_policy_config_when_loading_then_raises_clear_error(
    tmp_path: Path,
    test_case: PolicyConfigErrorTestCase,
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(test_case.source, encoding="utf-8")

    with pytest.raises(PolicyError, match=test_case.expected_error_pattern):
        load_policy_config(project_dir=tmp_path)


@pytest.mark.parametrize(
    "test_case",
    (
        SqlTestPolicyConfigTestCase(
            description="nested pipeline directory",
            source='[policy.sql_tests]\npipeline_directory = "chains/commerce"\n',
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

    config: PolicyConfig = load_policy_config(project_dir=tmp_path)

    assert config.sql_tests == SqlTestPolicyConfig(
        pipeline_directory=test_case.expected_pipeline_directory
    )


@pytest.mark.parametrize(
    "test_case",
    (
        PolicyLayoutConfigTestCase(
            description="custom levels and thresholds",
            source=(
                '[policy.layout]\nlevels = ["raw", "conformed/clean", "reporting"]\n'
                'domain_roots = ["sales/partner", "inventory/forecasting"]\n'
                "[policy.thresholds]\n"
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
    test_case: PolicyLayoutConfigTestCase,
    tmp_path: Path,
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        test_case.source,
        encoding="utf-8",
    )

    config: PolicyConfig = load_policy_config(project_dir=tmp_path)

    assert config.layout == LayoutConfig(
        levels=test_case.expected_levels,
        domain_roots=("sales/partner", "inventory/forecasting"),
    )
    assert config.thresholds == test_case.expected_thresholds
