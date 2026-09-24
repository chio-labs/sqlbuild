from __future__ import annotations

from pathlib import Path

import pytest

from scripts.dupscore.constants import (
    CATEGORY_EXACT,
    CATEGORY_NEAR_MISS,
    CATEGORY_RENAMED,
    CHANGE_CHANGED,
    CHANGE_NEW,
)
from scripts.dupscore.main.build_clone_report import build_clone_report
from scripts.dupscore.models import CloneAllowlistEntry, CloneReport, DupscoreConfig
from tests.unit.scripts.dupscore._helpers.contracts.forced_overrides.helpers import (
    CONTRACT_FILES,
    DELTA_PATH,
    RENDER_ORDERS_SQL,
    STORE_EXEMPTION,
    WRITE_ORDERS,
)
from tests.unit.scripts.dupscore.main.build_clone_report._test_types import (
    AllowlistTestCase,
    ClusterShapeTestCase,
    ContractExemptionReportTestCase,
    ContractExemptionSinceTestCase,
    ExcludedUnitTestCase,
    ForcedMemberOrderTestCase,
    PathFilterTestCase,
    ReportedPathTestCase,
    SeededCloneTestCase,
    SinceFilterTestCase,
    SinceUnchangedTestCase,
)
from tests.unit.scripts.dupscore.main.build_clone_report.helpers import (
    PYTHON_BASE,
    PYTHON_NEAR_MISS_COPY,
    clone_options,
    cluster_languages,
    cluster_member_flags,
    cluster_member_names,
    link_categories,
    member_changes,
    member_changes_by_name,
    reported_members,
    seed_repository,
)
from tests.unit.scripts.dupscore.main.build_report.helpers import (
    commit_all,
    initialize_repo,
    write_project_files,
)

_DELTA_HEADER: str = (
    "from sqlbuild.demo.contract.base_store import BaseStore\n\n\nclass DeltaStore(BaseStore):\n"
)
_VOLUNTARY_CLUSTERS: list[list[str]] = [
    ["AlphaStore._render_orders_sql", "BetaStore._render_orders_sql"],
    ["AlphaStore.delete_orders", "GammaStore.delete_orders"],
    ["BetaStore.read_orders", "OrdersConnection.read_orders"],
]


@pytest.mark.parametrize(
    "test_case",
    [
        SeededCloneTestCase(
            description="python copy with annotations and comments is exact",
            left_path="src/sqlbuild/alpha/orders.py",
            right_path="src/sqlbuild/beta/orders_copy.py",
            expected_category=CATEGORY_EXACT,
        ),
        SeededCloneTestCase(
            description="python method with renamed identifiers and literals is renamed",
            left_path="src/sqlbuild/alpha/orders.py",
            right_path="src/sqlbuild/beta/inventory.py",
            expected_category=CATEGORY_RENAMED,
        ),
        SeededCloneTestCase(
            description="python copy with extra statements is a near miss",
            left_path="src/sqlbuild/alpha/orders.py",
            right_path="src/sqlbuild/gamma/support.py",
            expected_category=CATEGORY_NEAR_MISS,
        ),
        SeededCloneTestCase(
            description="rust copy with different comments and visibility is exact",
            left_path="crates/demo-rules/src/lib.rs",
            right_path="crates/demo-rules/src/copy.rs",
            expected_category=CATEGORY_EXACT,
        ),
        SeededCloneTestCase(
            description="rust impl method with renamed identifiers is renamed",
            left_path="crates/demo-rules/src/lib.rs",
            right_path="crates/demo-rules/src/orders.rs",
            expected_category=CATEGORY_RENAMED,
        ),
        SeededCloneTestCase(
            description="rust copy with an extra guard and raw string is a near miss",
            left_path="crates/demo-rules/src/lib.rs",
            right_path="crates/demo-rules/src/products.rs",
            expected_category=CATEGORY_NEAR_MISS,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_seeded_clones_when_building_report_then_links_expected_category(
    test_case: SeededCloneTestCase,
    tmp_path: Path,
) -> None:
    repo_root: Path = seed_repository(tmp_path)

    report: CloneReport = build_clone_report(
        repo_root=repo_root, options=clone_options(), config=DupscoreConfig()
    )

    categories: dict[frozenset[str], str] = link_categories(report)
    assert categories[frozenset((test_case.left_path, test_case.right_path))] == (
        test_case.expected_category
    )


@pytest.mark.parametrize(
    "test_case",
    [
        ClusterShapeTestCase(
            description="each language forms one four-member cluster",
            expected_languages=[("python",), ("rust",)],
            expected_sizes=[4, 4],
        )
    ],
    ids=lambda case: case.description,
)
def test_given_seeded_clones_when_building_report_then_groups_transitive_clusters(
    test_case: ClusterShapeTestCase,
    tmp_path: Path,
) -> None:
    repo_root: Path = seed_repository(tmp_path)

    report: CloneReport = build_clone_report(
        repo_root=repo_root, options=clone_options(), config=DupscoreConfig()
    )

    assert cluster_languages(report) == test_case.expected_languages
    assert sorted(len(cluster.members) for cluster in report.clusters) == test_case.expected_sizes


@pytest.mark.parametrize(
    "test_case",
    [
        ExcludedUnitTestCase(
            description="unrelated python function is not reported",
            include_tests=False,
            name="parse_fulfillment_window",
            expected_reported=False,
        ),
        ExcludedUnitTestCase(
            description="short duplicated helper is below the size threshold",
            include_tests=False,
            name="add_quantities",
            expected_reported=False,
        ),
        ExcludedUnitTestCase(
            description="unrelated rust function is not reported",
            include_tests=False,
            name="parse_window",
            expected_reported=False,
        ),
        ExcludedUnitTestCase(
            description="copy inside a cfg(test) module is skipped by default",
            include_tests=False,
            name="inline_test_copy",
            expected_reported=False,
        ),
        ExcludedUnitTestCase(
            description="copy in a cfg(test) external module file is skipped by default",
            include_tests=False,
            name="external_test_copy",
            expected_reported=False,
        ),
        ExcludedUnitTestCase(
            description="copy inside a cfg(test) module is reported with include-tests",
            include_tests=True,
            name="inline_test_copy",
            expected_reported=True,
        ),
        ExcludedUnitTestCase(
            description="copy in a cfg(test) external module is reported with include-tests",
            include_tests=True,
            name="external_test_copy",
            expected_reported=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_seeded_tree_when_building_report_then_applies_unit_exclusions(
    test_case: ExcludedUnitTestCase,
    tmp_path: Path,
) -> None:
    repo_root: Path = seed_repository(tmp_path)

    report: CloneReport = build_clone_report(
        repo_root=repo_root,
        options=clone_options(include_tests=test_case.include_tests),
        config=DupscoreConfig(),
    )

    names: set[str] = {member.name for member in reported_members(report)}
    assert (test_case.name in names) is test_case.expected_reported


@pytest.mark.parametrize(
    "test_case",
    [
        ReportedPathTestCase(
            description="rust tests directory is skipped by default",
            include_tests=False,
            path="crates/demo-rules/tests/integration.rs",
            expected_reported=False,
        ),
        ReportedPathTestCase(
            description="rust tests directory is analyzed with include-tests",
            include_tests=True,
            path="crates/demo-rules/tests/integration.rs",
            expected_reported=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_rust_test_directory_when_building_report_then_respects_include_tests(
    test_case: ReportedPathTestCase,
    tmp_path: Path,
) -> None:
    repo_root: Path = seed_repository(tmp_path)

    report: CloneReport = build_clone_report(
        repo_root=repo_root,
        options=clone_options(include_tests=test_case.include_tests),
        config=DupscoreConfig(),
    )

    paths: set[str] = {member.path for member in reported_members(report)}
    assert (test_case.path in paths) is test_case.expected_reported


@pytest.mark.parametrize(
    "test_case",
    [
        AllowlistTestCase(
            description="entry covering both sides suppresses the rust clones",
            entries=(CloneAllowlistEntry(paths=("crates/*",), reason="Mirrored rule helpers."),),
            expected_languages=[("python",)],
            expected_allowlisted_pairs=6,
        ),
        AllowlistTestCase(
            description="entry covering only one side keeps the pair",
            entries=(
                CloneAllowlistEntry(
                    paths=("crates/demo-rules/src/lib.rs",), reason="Only one side."
                ),
            ),
            expected_languages=[("python",), ("rust",)],
            expected_allowlisted_pairs=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_clone_allowlist_when_building_report_then_suppresses_covered_pairs(
    test_case: AllowlistTestCase,
    tmp_path: Path,
) -> None:
    repo_root: Path = seed_repository(tmp_path)

    report: CloneReport = build_clone_report(
        repo_root=repo_root,
        options=clone_options(),
        config=DupscoreConfig(clone_allowlist=test_case.entries),
    )

    assert report.allowlisted_pairs == test_case.expected_allowlisted_pairs
    assert cluster_languages(report) == test_case.expected_languages


@pytest.mark.parametrize(
    "test_case",
    [
        PathFilterTestCase(
            description="glob keeps only clusters with a matching member",
            path_globs=("*/gamma/*",),
            expected_languages=[("python",)],
        ),
        PathFilterTestCase(
            description="glob without matches keeps nothing",
            path_globs=("docs/*",),
            expected_languages=[],
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_path_filter_when_building_report_then_keeps_matching_clusters(
    test_case: PathFilterTestCase,
    tmp_path: Path,
) -> None:
    repo_root: Path = seed_repository(tmp_path)

    report: CloneReport = build_clone_report(
        repo_root=repo_root,
        options=clone_options(path_globs=test_case.path_globs),
        config=DupscoreConfig(),
    )

    assert cluster_languages(report) == test_case.expected_languages


@pytest.mark.parametrize(
    "test_case",
    [
        SinceUnchangedTestCase(
            description="unchanged worktree reports nothing",
            changed_files={},
            expected_cluster_count=0,
        ),
        SinceUnchangedTestCase(
            description="edits outside clone members report nothing",
            changed_files={"src/sqlbuild/gamma/notes.py": "VALUE = 1\n"},
            expected_cluster_count=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_since_revision_without_clone_edits_when_building_report_then_reports_nothing(
    test_case: SinceUnchangedTestCase,
    tmp_path: Path,
) -> None:
    repo_root: Path = seed_repository(tmp_path)
    initialize_repo(repo_root)
    base_revision: str = commit_all(repo_root=repo_root, message="seed clones")
    write_project_files(repo_root=repo_root, files=test_case.changed_files)

    report: CloneReport = build_clone_report(
        repo_root=repo_root, options=clone_options(since=base_revision), config=DupscoreConfig()
    )

    assert len(report.clusters) == test_case.expected_cluster_count


@pytest.mark.parametrize(
    "test_case",
    [
        SinceFilterTestCase(
            description="untracked copy is new and keeps its cluster",
            changed_files={"src/sqlbuild/delta/branch_copy.py": PYTHON_BASE},
            expected_changes={
                "src/sqlbuild/delta/branch_copy.py": CHANGE_NEW,
                "src/sqlbuild/alpha/orders.py": None,
            },
        ),
        SinceFilterTestCase(
            description="edited clone member is marked changed",
            changed_files={
                "src/sqlbuild/gamma/support.py": PYTHON_NEAR_MISS_COPY.replace(
                    'result = ["support queues"]', 'result = ["support queue totals"]'
                )
            },
            expected_changes={
                "src/sqlbuild/gamma/support.py": CHANGE_CHANGED,
                "src/sqlbuild/alpha/orders.py": None,
            },
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_since_revision_when_building_report_then_marks_touched_members(
    test_case: SinceFilterTestCase,
    tmp_path: Path,
) -> None:
    repo_root: Path = seed_repository(tmp_path)
    initialize_repo(repo_root)
    base_revision: str = commit_all(repo_root=repo_root, message="seed clones")
    write_project_files(repo_root=repo_root, files=test_case.changed_files)

    report: CloneReport = build_clone_report(
        repo_root=repo_root, options=clone_options(since=base_revision), config=DupscoreConfig()
    )

    assert len(report.clusters) == 1
    changes: dict[str, str | None] = member_changes(report.clusters[0])
    assert {path: changes[path] for path in test_case.expected_changes} == (
        test_case.expected_changes
    )


@pytest.mark.parametrize(
    "test_case",
    [
        ContractExemptionReportTestCase(
            description="links between forced overrides are hidden, voluntary copies stay",
            entries=(STORE_EXEMPTION,),
            expected_clusters=_VOLUNTARY_CLUSTERS,
            expected_contract_exempt_members=3,
        ),
        ContractExemptionReportTestCase(
            description="without an exemption every override cluster is reported",
            entries=(),
            expected_clusters=sorted(
                [
                    *_VOLUNTARY_CLUSTERS,
                    ["AlphaStore.write_orders", "BaseStore.write_orders", "BetaStore.write_orders"],
                ]
            ),
            expected_contract_exempt_members=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_contract_exemption_when_building_report_then_hides_forced_overrides(
    test_case: ContractExemptionReportTestCase,
    tmp_path: Path,
) -> None:
    write_project_files(repo_root=tmp_path, files=CONTRACT_FILES)

    report: CloneReport = build_clone_report(
        repo_root=tmp_path,
        options=clone_options(),
        config=DupscoreConfig(contract_exemptions=test_case.entries),
    )

    assert cluster_member_names(report) == test_case.expected_clusters
    assert report.contract_exempt_members == test_case.expected_contract_exempt_members


@pytest.mark.parametrize(
    "test_case",
    [
        ContractExemptionSinceTestCase(
            description="new private helper copy is reported beside a hidden forced override",
            changed_files={DELTA_PATH: _DELTA_HEADER + WRITE_ORDERS + RENDER_ORDERS_SQL},
            expected_clusters=[
                [
                    "AlphaStore._render_orders_sql",
                    "BetaStore._render_orders_sql",
                    "DeltaStore._render_orders_sql",
                ]
            ],
            expected_member_changes={
                "AlphaStore._render_orders_sql": None,
                "BetaStore._render_orders_sql": None,
                "DeltaStore._render_orders_sql": CHANGE_NEW,
            },
        ),
        ContractExemptionSinceTestCase(
            description="new forced override alone reports nothing",
            changed_files={DELTA_PATH: _DELTA_HEADER + WRITE_ORDERS},
            expected_clusters=[],
            expected_member_changes={},
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_since_revision_with_contract_exemption_when_building_report_then_hides_forced(
    test_case: ContractExemptionSinceTestCase,
    tmp_path: Path,
) -> None:
    write_project_files(repo_root=tmp_path, files=CONTRACT_FILES)
    initialize_repo(tmp_path)
    base_revision: str = commit_all(repo_root=tmp_path, message="seed stores")
    write_project_files(repo_root=tmp_path, files=test_case.changed_files)

    report: CloneReport = build_clone_report(
        repo_root=tmp_path,
        options=clone_options(since=base_revision),
        config=DupscoreConfig(contract_exemptions=(STORE_EXEMPTION,)),
    )

    assert cluster_member_names(report) == test_case.expected_clusters
    assert member_changes_by_name(report) == test_case.expected_member_changes


@pytest.mark.parametrize(
    "test_case",
    [
        ForcedMemberOrderTestCase(
            description="voluntary copies are listed before flagged forced overrides",
            expected_member_flags=[
                [("AlphaStore._render_orders_sql", False), ("BetaStore._render_orders_sql", False)],
                [("GammaStore.delete_orders", False), ("AlphaStore.delete_orders", True)],
                [("OrdersConnection.read_orders", False), ("BetaStore.read_orders", True)],
            ],
        )
    ],
    ids=lambda case: case.description,
)
def test_given_contract_exemption_when_building_report_then_lists_forced_members_last(
    test_case: ForcedMemberOrderTestCase,
    tmp_path: Path,
) -> None:
    write_project_files(repo_root=tmp_path, files=CONTRACT_FILES)

    report: CloneReport = build_clone_report(
        repo_root=tmp_path,
        options=clone_options(),
        config=DupscoreConfig(contract_exemptions=(STORE_EXEMPTION,)),
    )

    assert cluster_member_flags(report) == test_case.expected_member_flags
