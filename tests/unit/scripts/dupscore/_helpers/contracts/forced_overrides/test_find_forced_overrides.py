from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from scripts.dupscore._helpers.contracts.forced_overrides import find_forced_overrides
from scripts.dupscore._helpers.inputs.config import load_config
from scripts.dupscore.exceptions import DupscoreConfigError
from scripts.dupscore.models import DupscoreConfig
from tests.unit.scripts.dupscore._helpers.contracts.forced_overrides._test_types import (
    ContractLookupErrorTestCase,
    ForcedOverrideTestCase,
    InactiveContractTestCase,
)
from tests.unit.scripts.dupscore._helpers.contracts.forced_overrides.helpers import (
    ALPHA_PATH,
    BASE_PATH,
    BETA_PATH,
    CONNECTION_PATH,
    CONTRACT_FILES,
    CONTRACT_PATH,
    GAMMA_PATH,
    OUTSIDE_PATH,
    STORE_EXEMPTION,
    method_unit,
)
from tests.unit.scripts.dupscore.main.build_report.helpers import write_project_files

_ADAPTER_CLASSES: str = "src/sqlbuild/adapter/contract/classes"
_ADAPTERS: str = "src/sqlbuild/adapters"


@pytest.mark.parametrize(
    "test_case",
    [
        ForcedOverrideTestCase(
            description="base class override of an abstractmethod is forced",
            language="python",
            path=BASE_PATH,
            name="BaseStore.write_orders",
            expected_forced=True,
        ),
        ForcedOverrideTestCase(
            description="subclass would otherwise inherit from a forbidden owner",
            language="python",
            path=ALPHA_PATH,
            name="AlphaStore.write_orders",
            expected_forced=True,
        ),
        ForcedOverrideTestCase(
            description="abc.abstractmethod declarations are contract methods",
            language="python",
            path=ALPHA_PATH,
            name="AlphaStore.delete_orders",
            expected_forced=True,
        ),
        ForcedOverrideTestCase(
            description="abstract methods inherited through an aliased mixin import count",
            language="python",
            path=BETA_PATH,
            name="BetaStore.read_orders",
            expected_forced=True,
        ),
        ForcedOverrideTestCase(
            description="stacked property and abstractmethod decorators count",
            language="python",
            path=BETA_PATH,
            name="BetaStore.store_name",
            expected_forced=True,
        ),
        ForcedOverrideTestCase(
            description="mixin abstract method made concrete by the contract is not a contract",
            language="python",
            path=ALPHA_PATH,
            name="AlphaStore.count_orders",
            expected_forced=False,
        ),
        ForcedOverrideTestCase(
            description="private helper methods are not contract methods",
            language="python",
            path=ALPHA_PATH,
            name="AlphaStore._render_orders_sql",
            expected_forced=False,
        ),
        ForcedOverrideTestCase(
            description="override that could inherit from an allowed ancestor is voluntary",
            language="python",
            path=GAMMA_PATH,
            name="GammaStore.delete_orders",
            expected_forced=False,
        ),
        ForcedOverrideTestCase(
            description="class that does not derive from the contract is not exempt",
            language="python",
            path=CONNECTION_PATH,
            name="OrdersConnection.read_orders",
            expected_forced=False,
        ),
        ForcedOverrideTestCase(
            description="contract subclass outside the listed paths is not exempt",
            language="python",
            path=OUTSIDE_PATH,
            name="OutsideStore.write_orders",
            expected_forced=False,
        ),
        ForcedOverrideTestCase(
            description="top-level functions named like contract methods are not exempt",
            language="python",
            path=ALPHA_PATH,
            name="write_orders",
            expected_forced=False,
        ),
        ForcedOverrideTestCase(
            description="rust units are never exempt",
            language="rust",
            path=ALPHA_PATH,
            name="AlphaStore.write_orders",
            expected_forced=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_contract_exemption_when_checking_unit_then_reports_forced_override(
    test_case: ForcedOverrideTestCase,
    tmp_path: Path,
) -> None:
    write_project_files(repo_root=tmp_path, files=CONTRACT_FILES)

    forced: tuple[bool, ...] = find_forced_overrides(
        repo_root=tmp_path,
        entries=(STORE_EXEMPTION,),
        units=[method_unit(language=test_case.language, path=test_case.path, name=test_case.name)],
    )

    assert forced == (test_case.expected_forced,)


@pytest.mark.parametrize(
    "test_case",
    [
        ContractLookupErrorTestCase(
            description="missing contract class in an existing file",
            entry=replace(STORE_EXEMPTION, contract_class="MissingStore"),
            expected_error_fragment=f"{CONTRACT_PATH}:MissingStore was not found",
        ),
        ContractLookupErrorTestCase(
            description="missing forbidden owner class",
            entry=replace(STORE_EXEMPTION, forbidden_owners=((BASE_PATH, "MissingBase"),)),
            expected_error_fragment=f"{BASE_PATH}:MissingBase was not found",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unresolvable_contract_class_when_loading_then_raises_config_error(
    test_case: ContractLookupErrorTestCase,
    tmp_path: Path,
) -> None:
    write_project_files(repo_root=tmp_path, files=CONTRACT_FILES)

    with pytest.raises(DupscoreConfigError) as raised:
        _ = find_forced_overrides(repo_root=tmp_path, entries=(test_case.entry,), units=[])

    assert test_case.expected_error_fragment in str(raised.value)


@pytest.mark.parametrize(
    "test_case",
    [
        InactiveContractTestCase(
            description="entry whose contract file is absent exempts nothing",
            entry=replace(STORE_EXEMPTION, contract_path="src/sqlbuild/demo/absent.py"),
            path=ALPHA_PATH,
            name="AlphaStore.write_orders",
            expected_forced=False,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_absent_contract_file_when_checking_unit_then_nothing_is_exempt(
    test_case: InactiveContractTestCase,
    tmp_path: Path,
) -> None:
    write_project_files(repo_root=tmp_path, files=CONTRACT_FILES)

    forced: tuple[bool, ...] = find_forced_overrides(
        repo_root=tmp_path,
        entries=(test_case.entry,),
        units=[method_unit(language="python", path=test_case.path, name=test_case.name)],
    )

    assert forced == (test_case.expected_forced,)


@pytest.mark.parametrize(
    "test_case",
    [
        ForcedOverrideTestCase(
            description="duckdb-backed contract override is forced",
            language="python",
            path=f"{_ADAPTER_CLASSES}/duckdb_backed_adapter.py",
            name="DuckDbBackedAdapter.connect",
            expected_forced=True,
        ),
        ForcedOverrideTestCase(
            description="motherduck override could inherit the duckdb-backed method",
            language="python",
            path=f"{_ADAPTERS}/motherduck/classes/motherduck_adapter.py",
            name="MotherDuckAdapter.connect",
            expected_forced=False,
        ),
        ForcedOverrideTestCase(
            description="base adapter contract method is forced",
            language="python",
            path=f"{_ADAPTER_CLASSES}/base_adapter.py",
            name="BaseAdapter.render_merge",
            expected_forced=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_shipped_contract_exemption_when_checking_repository_then_matches_contract(
    test_case: ForcedOverrideTestCase,
) -> None:
    repo_root: Path = Path(__file__).resolve().parents[7]
    config: DupscoreConfig = load_config(repo_root / "scripts/dupscore/dupscore.toml")

    forced: tuple[bool, ...] = find_forced_overrides(
        repo_root=repo_root,
        entries=config.contract_exemptions,
        units=[method_unit(language=test_case.language, path=test_case.path, name=test_case.name)],
    )

    assert forced == (test_case.expected_forced,)
