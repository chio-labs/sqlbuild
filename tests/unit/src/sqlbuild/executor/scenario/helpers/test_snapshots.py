from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.planner.models import ScenarioExecutionPlan
from sqlbuild.compiler.planner.types import ScenarioArtifactKind
from sqlbuild.executor.scenario.helpers.snapshots import (
    build_scenario_snapshot_input_fingerprint,
    build_scenario_snapshot_input_specs,
    classify_scenario_snapshot_state,
    is_scenario_snapshot_fresh,
    read_scenario_snapshot_manifest,
    scenario_snapshot_manifest_path,
    scenario_snapshot_relation_file_path,
    scenario_snapshot_root,
    write_scenario_snapshot_manifest,
)
from sqlbuild.executor.scenario.models import (
    ScenarioSnapshotInputSpec,
    ScenarioSnapshotManifest,
    ScenarioSnapshotStateResult,
)
from sqlbuild.executor.scenario.types import ScenarioSnapshotState
from tests.unit.src.sqlbuild.executor.scenario.helpers._test_types import (
    ScenarioSnapshotFingerprintTestCase,
    ScenarioSnapshotFreshnessTestCase,
    ScenarioSnapshotInputSpecsFromPlanTestCase,
    ScenarioSnapshotManifestIoTestCase,
    ScenarioSnapshotPathTestCase,
    ScenarioSnapshotRelationPathErrorTestCase,
    ScenarioSnapshotStateTestCase,
)
from tests.unit.src.sqlbuild.executor.scenario.helpers.helpers import (
    assert_snapshot_state_error,
    build_snapshot_input_specs_test_plan,
    build_snapshot_manifest,
    write_snapshot_state_test_manifest,
)

SNAPSHOT_STATE_PLAN: ScenarioExecutionPlan = build_snapshot_input_specs_test_plan()
SNAPSHOT_STATE_FINGERPRINT: str = build_scenario_snapshot_input_fingerprint(
    scenario_name=SNAPSHOT_STATE_PLAN.name,
    input_specs=build_scenario_snapshot_input_specs(scenario_plan=SNAPSHOT_STATE_PLAN),
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

SNAPSHOT_STATE_TEST_CASES: list[ScenarioSnapshotStateTestCase] = [
    ScenarioSnapshotStateTestCase(
        description="missing manifest is classified as missing",
        manifest=None,
        manifest_contents=None,
        expected_state=ScenarioSnapshotState.MISSING,
        expected_has_manifest=False,
    ),
    ScenarioSnapshotStateTestCase(
        description="matching fingerprint manifest is classified as fresh",
        manifest=build_snapshot_manifest(input_fingerprint=SNAPSHOT_STATE_FINGERPRINT),
        manifest_contents=None,
        expected_state=ScenarioSnapshotState.FRESH,
        expected_has_manifest=True,
    ),
    ScenarioSnapshotStateTestCase(
        description="different fingerprint manifest is classified as stale",
        manifest=build_snapshot_manifest(input_fingerprint="stale123"),
        manifest_contents=None,
        expected_state=ScenarioSnapshotState.STALE,
        expected_has_manifest=True,
    ),
    ScenarioSnapshotStateTestCase(
        description="malformed manifest is classified as invalid",
        manifest=None,
        manifest_contents="{not json",
        expected_state=ScenarioSnapshotState.INVALID,
        expected_has_manifest=False,
        expected_error_fragment="Invalid scenario snapshot manifest JSON",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    [
        ScenarioSnapshotManifestIoTestCase(
            description="manifest round trips through scenario json shape",
            manifest=build_snapshot_manifest(),
            expected_json_fragments=(
                '"file": "sources/raw__orders.jsonl"',
                '"bytes": 100',
                '"warehouse_type": "NUMBER(10,2)"',
                '"local_type": "DECIMAL(10,2)"',
            ),
        )
    ],
    ids=["manifest round trips through scenario json shape"],
)
def test_given_snapshot_manifest_when_writing_and_reading_then_round_trips_json_shape(
    tmp_path: Path,
    test_case: ScenarioSnapshotManifestIoTestCase,
) -> None:
    manifest_path: Path = scenario_snapshot_manifest_path(
        project_dir=tmp_path,
        scenario_name=test_case.manifest.scenario_name,
    )

    write_scenario_snapshot_manifest(
        manifest_path=manifest_path,
        manifest=test_case.manifest,
    )
    manifest_contents: str = manifest_path.read_text(encoding="utf-8")
    loaded_manifest: ScenarioSnapshotManifest = read_scenario_snapshot_manifest(
        manifest_path=manifest_path,
    )

    assert loaded_manifest == test_case.manifest
    for expected_fragment in test_case.expected_json_fragments:
        assert expected_fragment in manifest_contents


@pytest.mark.parametrize(
    "test_case",
    SNAPSHOT_STATE_TEST_CASES,
    ids=[case.description for case in SNAPSHOT_STATE_TEST_CASES],
)
def test_given_snapshot_manifest_state_when_classifying_then_returns_expected_state(
    tmp_path: Path,
    test_case: ScenarioSnapshotStateTestCase,
) -> None:
    manifest_path: Path = scenario_snapshot_manifest_path(
        project_dir=tmp_path,
        scenario_name=SNAPSHOT_STATE_PLAN.name,
    )
    write_snapshot_state_test_manifest(manifest_path=manifest_path, test_case=test_case)

    state_result: ScenarioSnapshotStateResult = classify_scenario_snapshot_state(
        project_dir=tmp_path,
        scenario_plan=SNAPSHOT_STATE_PLAN,
    )

    assert state_result.state == test_case.expected_state
    assert (state_result.manifest is not None) is test_case.expected_has_manifest
    assert_snapshot_state_error(state_result=state_result, test_case=test_case)


@pytest.mark.parametrize(
    "test_case",
    [
        ScenarioSnapshotInputSpecsFromPlanTestCase(
            description="scenario plan inputs become durable snapshot input specs",
            scenario_plan=build_snapshot_input_specs_test_plan(),
            expected_input_specs=(
                ScenarioSnapshotInputSpec(
                    kind=ScenarioArtifactKind.REF,
                    logical_name="stg_customers",
                    file_path=Path("refs/stg_customers.jsonl"),
                    capture_sql="SELECT 10 AS customer_id",
                ),
                ScenarioSnapshotInputSpec(
                    kind=ScenarioArtifactKind.SEED,
                    logical_name="country_codes",
                    file_path=Path("seeds/country_codes.jsonl"),
                    capture_sql="SELECT 'US' AS country_code",
                ),
                ScenarioSnapshotInputSpec(
                    kind=ScenarioArtifactKind.SEED,
                    logical_name="currency_codes",
                    file_path=Path("seeds/currency_codes.jsonl"),
                    capture_sql="seed_file:seeds/currency_codes.csv",
                ),
                ScenarioSnapshotInputSpec(
                    kind=ScenarioArtifactKind.SOURCE,
                    logical_name="raw__orders",
                    file_path=Path("sources/raw__orders.jsonl"),
                    capture_sql="SELECT 1 AS order_id",
                ),
            ),
            changed_check_plan=build_snapshot_input_specs_test_plan(
                expected_sql_suffix=" ORDER BY revenue"
            ),
            changed_fixture_plan=build_snapshot_input_specs_test_plan(
                fixture_sql_suffix=" WHERE order_id = 1"
            ),
            expected_check_fingerprint_matches=True,
            expected_fixture_fingerprint_differs=True,
        )
    ],
    ids=["scenario plan inputs become durable snapshot input specs"],
)
def test_given_scenario_execution_plan_when_building_snapshot_specs_then_returns_input_specs(
    test_case: ScenarioSnapshotInputSpecsFromPlanTestCase,
) -> None:
    input_specs: tuple[ScenarioSnapshotInputSpec, ...] = build_scenario_snapshot_input_specs(
        scenario_plan=test_case.scenario_plan,
    )
    fingerprint: str = build_scenario_snapshot_input_fingerprint(
        scenario_name=test_case.scenario_plan.name,
        input_specs=input_specs,
    )
    changed_check_fingerprint: str = build_scenario_snapshot_input_fingerprint(
        scenario_name=test_case.changed_check_plan.name,
        input_specs=build_scenario_snapshot_input_specs(
            scenario_plan=test_case.changed_check_plan,
        ),
    )
    changed_fixture_fingerprint: str = build_scenario_snapshot_input_fingerprint(
        scenario_name=test_case.changed_fixture_plan.name,
        input_specs=build_scenario_snapshot_input_specs(
            scenario_plan=test_case.changed_fixture_plan,
        ),
    )

    assert input_specs == test_case.expected_input_specs
    assert (fingerprint == changed_check_fingerprint) is (
        test_case.expected_check_fingerprint_matches
    )
    assert (fingerprint != changed_fixture_fingerprint) is (
        test_case.expected_fixture_fingerprint_differs
    )


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
