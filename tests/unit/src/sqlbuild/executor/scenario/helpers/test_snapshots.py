from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.planner.types import ScenarioArtifactKind
from sqlbuild.executor.scenario.helpers.snapshots import (
    build_scenario_snapshot_input_fingerprint,
    is_scenario_snapshot_fresh,
    scenario_snapshot_manifest_path,
    scenario_snapshot_relation_file_path,
    scenario_snapshot_root,
)
from sqlbuild.executor.scenario.models import (
    ScenarioSnapshotInputSpec,
    ScenarioSnapshotManifest,
)
from tests.unit.src.sqlbuild.executor.scenario.helpers._test_types import (
    ScenarioSnapshotFingerprintTestCase,
    ScenarioSnapshotFreshnessTestCase,
    ScenarioSnapshotPathTestCase,
    ScenarioSnapshotRelationPathErrorTestCase,
)

PATH_TEST_CASES: list[ScenarioSnapshotPathTestCase] = [
    ScenarioSnapshotPathTestCase(
        description="source snapshot paths use scenario snapshot root",
        project_dir=Path("/repo"),
        scenario_name="order_refund",
        kind=ScenarioArtifactKind.SOURCE,
        logical_name="raw__orders",
        expected_root=Path("/repo/tests/_scenario_snapshots/order_refund"),
        expected_manifest_path=Path("/repo/tests/_scenario_snapshots/order_refund/scenario.json"),
        expected_relation_path=Path("sources/raw__orders.jsonl"),
    ),
    ScenarioSnapshotPathTestCase(
        description="ref snapshot paths use refs directory",
        project_dir=Path("/repo"),
        scenario_name="order_refund",
        kind=ScenarioArtifactKind.REF,
        logical_name="stg_customers",
        expected_root=Path("/repo/tests/_scenario_snapshots/order_refund"),
        expected_manifest_path=Path("/repo/tests/_scenario_snapshots/order_refund/scenario.json"),
        expected_relation_path=Path("refs/stg_customers.jsonl"),
    ),
    ScenarioSnapshotPathTestCase(
        description="seed snapshot paths use seeds directory",
        project_dir=Path("/repo"),
        scenario_name="order_refund",
        kind=ScenarioArtifactKind.SEED,
        logical_name="waffle_types",
        expected_root=Path("/repo/tests/_scenario_snapshots/order_refund"),
        expected_manifest_path=Path("/repo/tests/_scenario_snapshots/order_refund/scenario.json"),
        expected_relation_path=Path("seeds/waffle_types.jsonl"),
    ),
]


FRESHNESS_TEST_CASES: list[ScenarioSnapshotFreshnessTestCase] = [
    ScenarioSnapshotFreshnessTestCase(
        description="matching input fingerprint is fresh",
        manifest_fingerprint="abc123",
        current_fingerprint="abc123",
        expected_is_fresh=True,
    ),
    ScenarioSnapshotFreshnessTestCase(
        description="different input fingerprint is stale",
        manifest_fingerprint="abc123",
        current_fingerprint="def456",
        expected_is_fresh=False,
    ),
]


@pytest.mark.parametrize(
    "test_case", PATH_TEST_CASES, ids=[case.description for case in PATH_TEST_CASES]
)
def test_given_scenario_and_relation_when_resolving_snapshot_paths_then_returns_expected_paths(
    test_case: ScenarioSnapshotPathTestCase,
) -> None:
    root: Path = scenario_snapshot_root(
        project_dir=test_case.project_dir,
        scenario_name=test_case.scenario_name,
    )
    manifest_path: Path = scenario_snapshot_manifest_path(
        project_dir=test_case.project_dir,
        scenario_name=test_case.scenario_name,
    )
    relation_path: Path = scenario_snapshot_relation_file_path(
        kind=test_case.kind,
        logical_name=test_case.logical_name,
    )

    assert root == test_case.expected_root
    assert manifest_path == test_case.expected_manifest_path
    assert relation_path == test_case.expected_relation_path


@pytest.mark.parametrize(
    "test_case",
    [
        ScenarioSnapshotFingerprintTestCase(
            description="fingerprint is stable across input ordering and SQL whitespace",
            scenario_name="order_refund",
            input_specs=(
                ScenarioSnapshotInputSpec(
                    kind=ScenarioArtifactKind.SOURCE,
                    logical_name="raw__orders",
                    file_path=Path("sources/raw__orders.jsonl"),
                    capture_sql="SELECT *\nFROM raw.orders",
                ),
                ScenarioSnapshotInputSpec(
                    kind=ScenarioArtifactKind.REF,
                    logical_name="stg_customers",
                    file_path=Path("refs/stg_customers.jsonl"),
                    capture_sql="SELECT * FROM analytics.stg_customers",
                ),
            ),
            equivalent_input_specs=(
                ScenarioSnapshotInputSpec(
                    kind=ScenarioArtifactKind.REF,
                    logical_name="stg_customers",
                    file_path=Path("refs/stg_customers.jsonl"),
                    capture_sql="SELECT   *   FROM analytics.stg_customers",
                ),
                ScenarioSnapshotInputSpec(
                    kind=ScenarioArtifactKind.SOURCE,
                    logical_name="raw__orders",
                    file_path=Path("sources/raw__orders.jsonl"),
                    capture_sql="SELECT * FROM raw.orders",
                ),
            ),
            changed_input_specs=(
                ScenarioSnapshotInputSpec(
                    kind=ScenarioArtifactKind.SOURCE,
                    logical_name="raw__orders",
                    file_path=Path("sources/raw__orders.jsonl"),
                    capture_sql="SELECT id FROM raw.orders",
                ),
                ScenarioSnapshotInputSpec(
                    kind=ScenarioArtifactKind.REF,
                    logical_name="stg_customers",
                    file_path=Path("refs/stg_customers.jsonl"),
                    capture_sql="SELECT * FROM analytics.stg_customers",
                ),
            ),
            expected_matches_equivalent=True,
            expected_differs_from_changed=True,
        )
    ],
    ids=["fingerprint is stable across input ordering and SQL whitespace"],
)
def test_given_snapshot_input_specs_when_fingerprinting_then_is_stable_and_input_sensitive(
    test_case: ScenarioSnapshotFingerprintTestCase,
) -> None:
    fingerprint: str = build_scenario_snapshot_input_fingerprint(
        scenario_name=test_case.scenario_name,
        input_specs=test_case.input_specs,
    )
    equivalent_fingerprint: str = build_scenario_snapshot_input_fingerprint(
        scenario_name=test_case.scenario_name,
        input_specs=test_case.equivalent_input_specs,
    )
    changed_fingerprint: str = build_scenario_snapshot_input_fingerprint(
        scenario_name=test_case.scenario_name,
        input_specs=test_case.changed_input_specs,
    )

    assert (fingerprint == equivalent_fingerprint) is test_case.expected_matches_equivalent
    assert (fingerprint != changed_fingerprint) is test_case.expected_differs_from_changed


@pytest.mark.parametrize(
    "test_case", FRESHNESS_TEST_CASES, ids=[case.description for case in FRESHNESS_TEST_CASES]
)
def test_given_manifest_and_current_fingerprint_when_checking_freshness_then_returns_expected_state(
    test_case: ScenarioSnapshotFreshnessTestCase,
) -> None:
    manifest: ScenarioSnapshotManifest = ScenarioSnapshotManifest(
        version=1,
        scenario_name="order_refund",
        captured_at="2026-05-09T00:00:00Z",
        capture_adapter="snowflake",
        capture_dialect="snowflake",
        sqlbuild_version="0.1.0",
        input_fingerprint=test_case.manifest_fingerprint,
        total_rows=0,
        total_bytes=0,
    )

    is_fresh: bool = is_scenario_snapshot_fresh(
        manifest=manifest,
        current_input_fingerprint=test_case.current_fingerprint,
    )

    assert is_fresh == test_case.expected_is_fresh


@pytest.mark.parametrize(
    "test_case",
    [
        ScenarioSnapshotRelationPathErrorTestCase(
            description="model artifacts are not captured as local snapshot relations",
            kind=ScenarioArtifactKind.MODEL,
            logical_name="fact_orders",
            expected_error_type=ValueError,
        )
    ],
    ids=["model artifacts are not captured as local snapshot relations"],
)
def test_given_unsupported_artifact_when_resolving_snapshot_path_then_raises_expected_error(
    test_case: ScenarioSnapshotRelationPathErrorTestCase,
) -> None:
    with pytest.raises(test_case.expected_error_type):
        scenario_snapshot_relation_file_path(
            kind=test_case.kind,
            logical_name=test_case.logical_name,
        )
