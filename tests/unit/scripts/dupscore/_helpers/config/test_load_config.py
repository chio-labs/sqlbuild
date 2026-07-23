from __future__ import annotations

from pathlib import Path

import pytest

from scripts.dupscore._helpers.config import load_config
from scripts.dupscore.exceptions import DupscoreConfigError
from scripts.dupscore.models import DupscoreConfig
from tests.unit.scripts.dupscore._helpers.config._test_types import (
    InvalidConfigTestCase,
    LoadConfigTestCase,
    MissingConfigTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        LoadConfigTestCase(
            description="loads surfaces and normalizes allowlist pair order",
            toml_text=(
                'persisted_state_surfaces = ["sqlbuild.virtual.state"]\n'
                "\n"
                "[[allowlist]]\n"
                'pair = ["sqlbuild.b.right", "sqlbuild.a.left"]\n'
                'reason = "intentional mirror"\n'
            ),
            expected_surfaces=("sqlbuild.virtual.state",),
            expected_allowlisted_pair=("sqlbuild.a.left", "sqlbuild.b.right"),
            expected_reason="intentional mirror",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_config_file_when_loading_then_returns_expected_config(
    test_case: LoadConfigTestCase,
    tmp_path: Path,
) -> None:
    config_path: Path = tmp_path / "dupscore.toml"
    config_path.write_text(test_case.toml_text, encoding="utf-8")

    config: DupscoreConfig = load_config(config_path)

    assert config.persisted_state_surfaces == test_case.expected_surfaces
    assert (
        config.allowlisted_pairs[test_case.expected_allowlisted_pair] == test_case.expected_reason
    )


@pytest.mark.parametrize(
    "test_case",
    [
        MissingConfigTestCase(
            description="returns empty config when the file is missing",
            expected_surfaces=(),
            expected_allowlist_size=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_missing_config_file_when_loading_then_returns_empty_config(
    test_case: MissingConfigTestCase,
    tmp_path: Path,
) -> None:
    config_path: Path = tmp_path / "dupscore.toml"

    config: DupscoreConfig = load_config(config_path)

    assert config.persisted_state_surfaces == test_case.expected_surfaces
    assert len(config.allowlisted_pairs) == test_case.expected_allowlist_size


@pytest.mark.parametrize(
    "test_case",
    [
        InvalidConfigTestCase(
            description="rejects allowlist entries without a reason",
            toml_text='[[allowlist]]\npair = ["sqlbuild.a", "sqlbuild.b"]\n',
            expected_error_fragment="reason",
        ),
        InvalidConfigTestCase(
            description="rejects non-list surfaces",
            toml_text='persisted_state_surfaces = "sqlbuild.virtual.state"\n',
            expected_error_fragment="persisted_state_surfaces",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_config_when_loading_then_raises_config_error(
    test_case: InvalidConfigTestCase,
    tmp_path: Path,
) -> None:
    config_path: Path = tmp_path / "dupscore.toml"
    config_path.write_text(test_case.toml_text, encoding="utf-8")

    with pytest.raises(DupscoreConfigError) as raised:
        _ = load_config(config_path)

    assert test_case.expected_error_fragment in str(raised.value)
