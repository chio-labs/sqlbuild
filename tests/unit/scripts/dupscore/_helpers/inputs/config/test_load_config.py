from __future__ import annotations

from pathlib import Path

import pytest

from scripts.dupscore._helpers.inputs.config import load_config
from scripts.dupscore.exceptions import DupscoreConfigError
from scripts.dupscore.models import CloneAllowlistEntry, ContractExemptionEntry, DupscoreConfig
from tests.unit.scripts.dupscore._helpers.inputs.config._test_types import (
    CloneAllowlistTestCase,
    ContractExemptionConfigTestCase,
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
        InvalidConfigTestCase(
            description="rejects contract exemptions without a reason",
            toml_text=(
                "[[contract_exemption]]\n"
                'contract = "src/demo/contract.py:StrictStore"\n'
                'paths = ["src/demo/*"]\n'
            ),
            expected_error_fragment="contract_exemption entry 1 needs a non-empty reason",
        ),
        InvalidConfigTestCase(
            description="rejects contract specs without a class name",
            toml_text=(
                "[[contract_exemption]]\n"
                'contract = "src/demo/contract.py"\n'
                'paths = ["src/demo/*"]\n'
                'reason = "forced"\n'
            ),
            expected_error_fragment="contract_exemption entry 1 contract must be",
        ),
        InvalidConfigTestCase(
            description="rejects contract specs that are not python files",
            toml_text=(
                "[[contract_exemption]]\n"
                'contract = "src/demo/contract.rs:StrictStore"\n'
                'paths = ["src/demo/*"]\n'
                'reason = "forced"\n'
            ),
            expected_error_fragment="contract_exemption entry 1 contract must be",
        ),
        InvalidConfigTestCase(
            description="rejects absolute contract paths",
            toml_text=(
                "[[contract_exemption]]\n"
                'contract = "/src/demo/contract.py:StrictStore"\n'
                'paths = ["src/demo/*"]\n'
                'reason = "forced"\n'
            ),
            expected_error_fragment="contract_exemption entry 1 contract must be",
        ),
        InvalidConfigTestCase(
            description="rejects contract class names that are not identifiers",
            toml_text=(
                "[[contract_exemption]]\n"
                'contract = "src/demo/contract.py:Strict.Store"\n'
                'paths = ["src/demo/*"]\n'
                'reason = "forced"\n'
            ),
            expected_error_fragment="contract_exemption entry 1 contract must be",
        ),
        InvalidConfigTestCase(
            description="rejects contract exemptions without a contract",
            toml_text='[[contract_exemption]]\npaths = ["src/demo/*"]\nreason = "forced"\n',
            expected_error_fragment="contract_exemption entry 1 contract must be",
        ),
        InvalidConfigTestCase(
            description="rejects contract exemptions without paths",
            toml_text=(
                "[[contract_exemption]]\n"
                'contract = "src/demo/contract.py:StrictStore"\n'
                'reason = "forced"\n'
            ),
            expected_error_fragment="contract_exemption entry 1 needs a non-empty paths list",
        ),
        InvalidConfigTestCase(
            description="rejects malformed forbidden owners",
            toml_text=(
                "[[contract_exemption]]\n"
                'contract = "src/demo/contract.py:StrictStore"\n'
                'forbidden_owners = ["BaseStore"]\n'
                'paths = ["src/demo/*"]\n'
                'reason = "forced"\n'
            ),
            expected_error_fragment="contract_exemption entry 1 forbidden_owners must be",
        ),
        InvalidConfigTestCase(
            description="rejects a non-list forbidden owners value",
            toml_text=(
                "[[contract_exemption]]\n"
                'contract = "src/demo/contract.py:StrictStore"\n'
                'forbidden_owners = "src/demo/base.py:BaseStore"\n'
                'paths = ["src/demo/*"]\n'
                'reason = "forced"\n'
            ),
            expected_error_fragment="contract_exemption entry 1 forbidden_owners must be a list",
        ),
        InvalidConfigTestCase(
            description="rejects contract exemptions with unknown keys",
            toml_text=(
                "[[contract_exemption]]\n"
                'contract = "src/demo/contract.py:StrictStore"\n'
                'paths = ["src/demo/*"]\n'
                'reason = "forced"\n'
                'methods = ["write_orders"]\n'
            ),
            expected_error_fragment="contract_exemption entry 1 has unknown keys: methods",
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
            expected_contract_exemption_size=1,
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
    assert len(config.contract_exemptions) == test_case.expected_contract_exemption_size


@pytest.mark.parametrize(
    "test_case",
    [
        ContractExemptionConfigTestCase(
            description="loads contract, forbidden owners, globs, and the stripped reason",
            toml_text=(
                "[[contract_exemption]]\n"
                'contract = "src/demo/contract.py:StrictStore"\n'
                'forbidden_owners = ["src/demo/base.py:BaseStore"]\n'
                'paths = ["src/demo/stores/*"]\n'
                'reason = " Stores must define every contract method. "\n'
            ),
            expected_entries=(
                ContractExemptionEntry(
                    contract_path="src/demo/contract.py",
                    contract_class="StrictStore",
                    paths=("src/demo/stores/*",),
                    reason="Stores must define every contract method.",
                    forbidden_owners=(("src/demo/base.py", "BaseStore"),),
                ),
            ),
        ),
        ContractExemptionConfigTestCase(
            description="forbidden owners are optional",
            toml_text=(
                "[[contract_exemption]]\n"
                'contract = "src/demo/contract.py:StrictStore"\n'
                'paths = ["src/demo/stores/*"]\n'
                'reason = "forced"\n'
            ),
            expected_entries=(
                ContractExemptionEntry(
                    contract_path="src/demo/contract.py",
                    contract_class="StrictStore",
                    paths=("src/demo/stores/*",),
                    reason="forced",
                ),
            ),
        ),
        ContractExemptionConfigTestCase(
            description="missing contract exemptions are empty",
            toml_text="",
            expected_entries=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_contract_exemption_when_loading_then_returns_entries(
    test_case: ContractExemptionConfigTestCase,
    tmp_path: Path,
) -> None:
    config_path: Path = tmp_path / "dupscore.toml"
    config_path.write_text(test_case.toml_text, encoding="utf-8")

    config: DupscoreConfig = load_config(config_path)

    assert config.contract_exemptions == test_case.expected_entries
