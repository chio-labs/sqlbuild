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
