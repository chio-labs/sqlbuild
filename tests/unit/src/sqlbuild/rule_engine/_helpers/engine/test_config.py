"""Strict rules configuration behavior tests."""

from pathlib import Path

import pytest

from sqlbuild.rule_engine.exceptions import RulesError
from sqlbuild.rule_engine.main.load_config import load_rules_config
from sqlbuild.rule_engine.models import LayoutConfig, RulesConfig, SqlTestRulesConfig
from tests.unit.src.sqlbuild.rule_engine._helpers.engine._test_types import (
    PolicyLayoutConfigTestCase,
    RuleIgnoreConfigTestCase,
    RulesConfigErrorTestCase,
    SqlTestRulesConfigTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (
        RulesConfigErrorTestCase(
            description="empty layout levels",
            source="[rules.layout]\nlevels = []\n",
            expected_error_pattern="rules.layout.levels must contain at least one",
        ),
        RulesConfigErrorTestCase(
            description="traversing layout level",
            source='[rules.layout]\nlevels = ["../staging"]\n',
            expected_error_pattern="must be normalized project-relative paths",
        ),
        RulesConfigErrorTestCase(
            description="duplicate layout level",
            source='[rules.layout]\nlevels = ["staging", "staging"]\n',
            expected_error_pattern="duplicate rules layout level: staging",
        ),
        RulesConfigErrorTestCase(
            description="overlapping layout levels",
            source=('[rules.layout]\nlevels = ["intermediate", "intermediate/enriched"]\n'),
            expected_error_pattern="rules.layout.levels entries must not overlap",
        ),
        RulesConfigErrorTestCase(
            description="overlapping explicit domain roots",
            source=('[rules.layout]\ndomain_roots = ["sales", "sales/partner"]\n'),
            expected_error_pattern="rules.layout.domain_roots entries must not overlap",
        ),
        RulesConfigErrorTestCase(
            description="unknown top-level key",
            source='[rules]\nselect = ["SQBRMODEL"]\nseverity = "warn"\n',
            expected_error_pattern="unknown rules config keys: severity",
        ),
        RulesConfigErrorTestCase(
            description="removed legacy rules section",
            source='[kata]\nselect = ["SQBK"]\n',
            expected_error_pattern="unsupported legacy rules configuration",
        ),
        RulesConfigErrorTestCase(
            description="unknown threshold",
            source="[rules.thresholds]\nmax_models = 3\n",
            expected_error_pattern="unknown rule thresholds: max_models",
        ),
        RulesConfigErrorTestCase(
            description="reasonless ignore",
            source=('[[rules.rule_ignores]]\nrules = ["SQBRMODEL"]\npaths = ["models/**"]\n'),
            expected_error_pattern="rules.rule_ignores.reason",
        ),
        RulesConfigErrorTestCase(
            description="ignore without resource scope",
            source=(
                '[[rules.rule_ignores]]\nrules = ["SQBRMODEL"]\nreason = "A reviewed exception"\n'
            ),
            expected_error_pattern="requires rules, paths or selectors, and reason",
        ),
        RulesConfigErrorTestCase(
            description="ignore with empty selector",
            source=(
                '[[rules.rule_ignores]]\nrules = ["SQBRMODEL"]\nselectors = [""]\n'
                'reason = "A reviewed exception"\n'
            ),
            expected_error_pattern="rule ignore selectors must be non-empty",
        ),
        RulesConfigErrorTestCase(
            description="ignore with empty path",
            source=(
                '[[rules.rule_ignores]]\nrules = ["SQBRMODEL"]\npaths = [""]\n'
                'reason = "A reviewed exception"\n'
            ),
            expected_error_pattern="rule ignore paths must be non-empty",
        ),
        RulesConfigErrorTestCase(
            description="reasonless threshold override",
            source=(
                '[[rules.threshold_overrides]]\npaths = ["models/mart/**"]\n'
                "thresholds = { min_tests_per_model = 2 }\n"
            ),
            expected_error_pattern="rules.threshold_overrides.reason",
        ),
        RulesConfigErrorTestCase(
            description="unknown scoped threshold",
            source=(
                '[[rules.threshold_overrides]]\npaths = ["models/mart/**"]\n'
                'reason = "marts need stronger coverage"\n'
                "thresholds = { max_models = 2 }\n"
            ),
            expected_error_pattern="unknown rule threshold override: max_models",
        ),
        RulesConfigErrorTestCase(
            description="project-wide threshold used as path override",
            source=(
                '[[rules.threshold_overrides]]\npaths = ["models/mart/**"]\n'
                'reason = "custom rule evidence is project-wide"\n'
                "thresholds = { min_custom_rule_test_cases = 2 }\n"
            ),
            expected_error_pattern=("unknown rule threshold override: min_custom_rule_test_cases"),
        ),
        RulesConfigErrorTestCase(
            description="invalid threshold override glob",
            source=(
                '[[rules.threshold_overrides]]\npaths = ["models/["]\n'
                'reason = "invalid migration pattern"\n'
                "thresholds = { min_tests_per_model = 2 }\n"
            ),
            expected_error_pattern="invalid rule threshold override path",
        ),
        RulesConfigErrorTestCase(
            description="empty threshold override glob",
            source=(
                '[[rules.threshold_overrides]]\npaths = [""]\n'
                'reason = "empty migration pattern"\n'
                "thresholds = { min_tests_per_model = 2 }\n"
            ),
            expected_error_pattern="threshold override paths must be non-empty globs",
        ),
        RulesConfigErrorTestCase(
            description="transitional rule namespace",
            source='[rules]\nselect = ["KTS"]\n',
            expected_error_pattern="malformed rule selector: KTS",
        ),
        RulesConfigErrorTestCase(
            description="absolute pipeline directory",
            source='[rules.sql_tests]\npipeline_directory = "/pipelines"\n',
            expected_error_pattern="must be a normalized path relative to tests/unit",
        ),
        RulesConfigErrorTestCase(
            description="traversing pipeline directory",
            source='[rules.sql_tests]\npipeline_directory = "../pipelines"\n',
            expected_error_pattern="must be a normalized path relative to tests/unit",
        ),
        RulesConfigErrorTestCase(
            description="unnormalized pipeline directory",
            source='[rules.sql_tests]\npipeline_directory = "chains//commerce"\n',
            expected_error_pattern="must be a normalized path relative to tests/unit",
        ),
        RulesConfigErrorTestCase(
            description="unknown SQL test rules key",
            source='[rules.sql_tests]\npipeline_directory = "pipelines"\nroot = "tests"\n',
            expected_error_pattern="unknown field `root`",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_invalid_rules_config_when_loading_then_raises_clear_error(
    tmp_path: Path,
    test_case: RulesConfigErrorTestCase,
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(test_case.source, encoding="utf-8")

    with pytest.raises(RulesError, match=test_case.expected_error_pattern):
        load_rules_config(project_dir=tmp_path)


@pytest.mark.parametrize(
    "test_case",
    (
        SqlTestRulesConfigTestCase(
            description="nested pipeline directory",
            source='[rules.sql_tests]\npipeline_directory = "chains/commerce"\n',
            expected_pipeline_directory="chains/commerce",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_pipeline_directory_when_loading_then_returns_typed_relative_configuration(
    tmp_path: Path,
    test_case: SqlTestRulesConfigTestCase,
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(test_case.source, encoding="utf-8")

    config: RulesConfig = load_rules_config(project_dir=tmp_path)

    assert config.sql_tests == SqlTestRulesConfig(
        pipeline_directory=test_case.expected_pipeline_directory
    )


@pytest.mark.parametrize(
    "test_case",
    (
        RuleIgnoreConfigTestCase(
            description="graph selectors and paths can share one scoped ignore",
            source=(
                '[[rules.rule_ignores]]\nrules = ["SQBRSQL021"]\n'
                'paths = ["tests/**"]\nselectors = ["+orders", "tag:interface+"]\n'
                'reason = "Reviewed interface resources"\n'
            ),
            expected_paths=("tests/**",),
            expected_selectors=("+orders", "tag:interface+"),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_scoped_ignore_selectors_when_loading_then_returns_typed_configuration(
    test_case: RuleIgnoreConfigTestCase,
    tmp_path: Path,
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(test_case.source, encoding="utf-8")

    config: RulesConfig = load_rules_config(project_dir=tmp_path)

    assert config.rule_ignores[0].paths == test_case.expected_paths
    assert config.rule_ignores[0].selectors == test_case.expected_selectors


@pytest.mark.parametrize(
    "test_case",
    (
        PolicyLayoutConfigTestCase(
            description="custom levels and thresholds",
            source=(
                '[rules.layout]\nlevels = ["raw", "conformed/clean", "reporting"]\n'
                'domain_roots = ["sales/partner", "inventory/forecasting"]\n'
                "[rules.thresholds]\n"
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

    config: RulesConfig = load_rules_config(project_dir=tmp_path)

    assert config.layout == LayoutConfig(
        levels=test_case.expected_levels,
        domain_roots=("sales/partner", "inventory/forecasting"),
    )
    assert config.thresholds == test_case.expected_thresholds
