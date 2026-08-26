"""Strict kata configuration behavior tests."""

from pathlib import Path

import pytest

from sqlbuild.kata_engine.exceptions import KataError
from sqlbuild.kata_engine.main.load_config import load_kata_config
from tests.unit.src.sqlbuild.kata_engine._helpers.engine._test_types import (
    KataConfigErrorTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (
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
