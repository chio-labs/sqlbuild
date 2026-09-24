from __future__ import annotations

from pathlib import Path

import pytest

from scripts.dupscore._helpers.inputs.config import load_config
from scripts.dupscore.exceptions import DupscoreConfigError
from scripts.dupscore.models import CloneAllowlistEntry, DupscoreConfig
from tests.unit.scripts.dupscore._helpers.inputs.config._test_types import (
    CloneAllowlistTestCase,
    InvalidConfigTestCase,
    LoadConfigTestCase,
    MissingConfigTestCase,
    ShippedConfigTestCase,
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
        InvalidConfigTestCase(
            description="rejects clone allowlist entries without a reason",
            toml_text='[[clone_allowlist]]\npaths = ["crates/*"]\nreason = "  "\n',
            expected_error_fragment="clone_allowlist entry 1 needs a non-empty reason",
        ),
        InvalidConfigTestCase(
            description="rejects clone allowlist entries with empty paths",
            toml_text='[[clone_allowlist]]\npaths = []\nreason = "mirror"\n',
            expected_error_fragment="clone_allowlist entry 1 needs a non-empty paths list",
        ),
        InvalidConfigTestCase(
            description="rejects clone allowlist entries with blank globs",
            toml_text='[[clone_allowlist]]\npaths = ["src/*", ""]\nreason = "mirror"\n',
            expected_error_fragment="non-empty glob strings",
        ),
        InvalidConfigTestCase(
            description="rejects clone allowlist entries with unknown keys",
            toml_text=(
                '[[clone_allowlist]]\npaths = ["src/*"]\nreason = "mirror"\npair = ["a", "b"]\n'
            ),
            expected_error_fragment="unknown keys: pair",
        ),
        InvalidConfigTestCase(
            description="rejects a non-table clone allowlist",
            toml_text='clone_allowlist = ["src/*"]\n',
            expected_error_fragment="clone_allowlist entry 1 must be a table",
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


@pytest.mark.parametrize(
    "test_case",
    [
        CloneAllowlistTestCase(
            description="loads clone allowlist globs and strips the reason",
            toml_text=(
                '[[clone_allowlist]]\npaths = ["src/sqlbuild/example/*", "crates/*"]\n'
                'reason = " Backends mirror one protocol. "\n'
            ),
            expected_entries=(
                CloneAllowlistEntry(
                    paths=("src/sqlbuild/example/*", "crates/*"),
                    reason="Backends mirror one protocol.",
                ),
            ),
        ),
        CloneAllowlistTestCase(
            description="missing clone allowlist is empty",
            toml_text="",
            expected_entries=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_clone_allowlist_when_loading_then_returns_entries(
    test_case: CloneAllowlistTestCase,
    tmp_path: Path,
) -> None:
    config_path: Path = tmp_path / "dupscore.toml"
    config_path.write_text(test_case.toml_text, encoding="utf-8")

    config: DupscoreConfig = load_config(config_path)

    assert config.clone_allowlist == test_case.expected_entries


@pytest.mark.parametrize(
    "test_case",
    [
        ShippedConfigTestCase(
            description="shipped dupscore.toml is valid",
            relative_path="scripts/dupscore/dupscore.toml",
            expected_pair_allowlist_size=9,
            expected_clone_allowlist_size=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_shipped_config_when_loading_then_it_is_valid(
    test_case: ShippedConfigTestCase,
) -> None:
    config_path: Path = Path(__file__).resolve().parents[7] / test_case.relative_path

    config: DupscoreConfig = load_config(config_path)

    assert len(config.allowlisted_pairs) == test_case.expected_pair_allowlist_size
    assert len(config.clone_allowlist) == test_case.expected_clone_allowlist_size
