from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Generator, Iterator, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Event
from typing import Any, cast
from unittest.mock import Mock

import pytest
from _pytest.capture import CaptureResult

from sqlbuild.cli.output._helpers.maximum_start_safety import serialize_maximum_start_safety
from sqlbuild.cli.output.models import IntegrationCheckResult, IntegrationResultEnvelope
from sqlbuild.compiler.planner.models import MaximumStartSafetyEvidence
from sqlbuild.integrations.dagster import (
    SqlBuildCliResource,
    SqlBuildDagsterTranslator,
)
from sqlbuild.integrations.dagster._helpers.invocation import (
    _build_results_from_execution_payload,
    _build_results_from_integration_result,
)
from sqlbuild.integrations.dagster.classes.sqlbuild_cli_invocation import SqlBuildCliInvocation
from sqlbuild.spec.contracts.types import FutureCursorAction, MicrobatchLimitAction
from tests.unit.src.sqlbuild.integrations.dagster._test_types import (
    DagsterAuditIdentityTestCase,
    DagsterCliCloneFailureTestCase,
    DagsterCliCloneStreamTestCase,
    DagsterCliFailureTestCase,
    DagsterCliInvocationTestCase,
    DagsterCliJsonStreamTestCase,
    DagsterCliLiveCloneEventTestCase,
    DagsterCliLiveLogTestCase,
    DagsterCliSelectionTestCase,
    DagsterCliStreamTestCase,
    DagsterFutureCursorMetadataTestCase,
    DagsterLiveFailureLoggingTestCase,
    DagsterManagedLoaderRoutingTestCase,
    DagsterMeasurementMetadataTestCase,
    DagsterMicrobatchLimitMetadataTestCase,
    DagsterSelectedCheckTestCase,
    DagsterTranslatorRuntimeTestCase,
)
from tests.unit.src.sqlbuild.integrations.dagster.helpers import (
    assert_json_output_file_behavior,
    assert_positional_selector_behavior,
    assert_select_file_selector_behavior,
    build_check_integration_envelope,
    build_dagster_test_dag,
    integration_result_payload,
    write_blocking_execution_event_command,
    write_blocking_failed_execution_event_command,
    write_blocking_fake_sqb_command,
    write_dagster_test_dag,
    write_fake_sqb_command,
    write_python_augmented_dagster_test_dag,
)

dg: Any = pytest.importorskip("dagster")


class _NamespacedDagsterTranslator(SqlBuildDagsterTranslator):
    def get_asset_key(self, node: Mapping[str, Any]) -> Any:
        return dg.AssetKey(["translated", str(node["name"])])

    def get_check_name(self, check: Mapping[str, Any]) -> str:
        return f"translated__{check['name']}"

    def is_asset_node(self, node: Mapping[str, Any]) -> bool:
        return str(node.get("kind")) != "source"


@pytest.mark.parametrize(
    "test_case",
    (
        DagsterManagedLoaderRoutingTestCase(
            description="same envelope loader satisfies source dependency",
            expected_asset_paths=(("raw_orders_loader",), ("raw", "orders")),
            expected_loader_id="loader:raw_orders_loader",
            expected_loader_name="raw_orders_loader",
            expected_source_name="raw_orders",
            expected_source_relation="analytics.raw_orders",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_managed_source_live_envelope_when_projecting_then_related_loader_and_source_emit_once(
    test_case: DagsterManagedLoaderRoutingTestCase,
) -> None:
    envelope: IntegrationResultEnvelope = IntegrationResultEnvelope.from_json(
        json.dumps(
            integration_result_payload(
                command="load",
                asset={
                    "kind": "source",
                    "name": "raw_orders",
                    "status": "success",
                    "loader": "raw_orders_loader",
                    "target": test_case.expected_source_relation,
                },
            )
        )
    )

    results: tuple[Any, ...] = _build_results_from_integration_result(
        dg=dg,
        dag=build_dagster_test_dag(),
        envelope=envelope,
        command=("sqb", "load"),
        context=type("LoaderContext", (), {"selected_asset_keys": set()})(),
        emitted_asset_paths=set(),
    )

    assert (
        tuple(tuple(result.asset_key.path) for result in results) == test_case.expected_asset_paths
    )
    loader_metadata: Any = results[0].metadata
    assert loader_metadata["sqlbuild_id"] == test_case.expected_loader_id
    assert loader_metadata["resource_id"] == test_case.expected_loader_id
    assert loader_metadata["kind"] == "loader"
    assert loader_metadata["name"] == test_case.expected_loader_name
    assert loader_metadata["source"] == test_case.expected_source_name
    assert loader_metadata["source_relation"] == test_case.expected_source_relation


@pytest.mark.parametrize(
    "test_case",
    (
        DagsterManagedLoaderRoutingTestCase(
            description="final source resolves explicitly named loader",
            expected_asset_paths=(("raw_orders_loader",), ("raw", "orders")),
            expected_loader_id="loader:raw_orders_loader",
            expected_loader_name="raw_orders_loader",
            expected_source_name="raw_orders",
            expected_source_relation="analytics.raw_orders",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_managed_source_final_payload_when_projecting_then_only_named_loader_and_source_emit(
    test_case: DagsterManagedLoaderRoutingTestCase,
) -> None:
    payload: dict[str, object] = {
        "version": 1,
        "command": "load",
        "assets": [
            {
                "kind": "loader",
                "name": "raw_orders",
                "status": "success",
                "loader": test_case.expected_loader_name,
                "target": test_case.expected_source_relation,
            }
        ],
        "checks": [],
    }

    results: tuple[Any, ...] = _build_results_from_execution_payload(
        dg=dg,
        dag=build_dagster_test_dag(),
        payload=payload,
        command=("sqb", "load"),
        context=type("LoaderContext", (), {"selected_asset_keys": set()})(),
    )

    assert (
        tuple(tuple(result.asset_key.path) for result in results) == test_case.expected_asset_paths
    )
    assert results[0].metadata["sqlbuild_id"] == test_case.expected_loader_id
    assert results[0].metadata["name"] == test_case.expected_loader_name


@pytest.mark.parametrize(
    "test_case",
    (DagsterSelectedCheckTestCase("model-only final payload omits unrelated source", "", False),),
    ids=lambda case: case.description,
)
def test_given_model_only_final_payload_when_projecting_then_no_source_observation_is_synthesized(
    test_case: DagsterSelectedCheckTestCase,
) -> None:
    results: tuple[Any, ...] = _build_results_from_execution_payload(
        dg=dg,
        dag=build_dagster_test_dag(),
        payload={
            "version": 1,
            "command": "build",
            "assets": [{"kind": "model", "name": "customers", "status": "success"}],
            "checks": [],
        },
        command=("sqb", "build"),
        context=type("ModelContext", (), {"selected_asset_keys": set()})(),
    )

    assert tuple(tuple(result.asset_key.path) for result in results) == (
        ("analytics", "customers"),
    )
    assert test_case.expected_output_path_retained is False


@pytest.mark.parametrize(
    "test_case",
    (
        DagsterAuditIdentityTestCase(
            description="two audit checks retain independent canonical identity",
            expected_event_ids=("event-not-null", "event-unique"),
            expected_attempt_ids=("attempt-not-null", "attempt-unique"),
            expected_resource_ids=(
                "audit:not_null:model:orders:order_id",
                "audit:unique:model:orders:order_id",
            ),
            expected_sequences=(3, 4),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_two_audit_envelopes_when_projecting_then_each_check_keeps_own_canonical_identity(
    test_case: DagsterAuditIdentityTestCase,
) -> None:
    dag: dict[str, Any] = dict(build_dagster_test_dag())
    dag["checks"] = [
        *dag["checks"],
        {
            "id": "audit:unique:model:orders:order_id",
            "kind": "audit",
            "name": "unique",
            "checked_asset_ids": ["model:orders"],
            "attached_column_name": "order_id",
        },
    ]
    envelopes: tuple[IntegrationResultEnvelope, ...] = (
        build_check_integration_envelope(
            check_id=test_case.expected_resource_ids[0],
            name="not_null",
            event_id=test_case.expected_event_ids[0],
            attempt_id=test_case.expected_attempt_ids[0],
            event_sequence=test_case.expected_sequences[0],
        ),
        build_check_integration_envelope(
            check_id=test_case.expected_resource_ids[1],
            name="unique",
            event_id=test_case.expected_event_ids[1],
            attempt_id=test_case.expected_attempt_ids[1],
            event_sequence=test_case.expected_sequences[1],
        ),
    )
    context: Any = type("AuditContext", (), {"selected_asset_keys": set()})()
    results: list[Any] = []
    for envelope in envelopes:
        results.extend(
            _build_results_from_integration_result(
                dg=dg,
                dag=dag,
                envelope=envelope,
                command=("sqb", "audit"),
                context=context,
                emitted_asset_paths={("analytics", "orders")},
            )
        )

    assert tuple(result.metadata["event_id"].value for result in results) == (
        test_case.expected_event_ids
    )
    assert tuple(result.metadata["resource_attempt_id"].value for result in results) == (
        test_case.expected_attempt_ids
    )
    assert tuple(result.metadata["resource_id"].value for result in results) == (
        test_case.expected_resource_ids
    )
    assert tuple(result.metadata["event_sequence"].value for result in results) == (
        test_case.expected_sequences
    )


@pytest.mark.parametrize(
    "test_case",
    (
        DagsterMeasurementMetadataTestCase(
            "insufficient measurement metadata",
            "insufficient",
            True,
            {
                "evaluation_mode": "measurement",
                "measured_value": 99.5,
                "sample_count": 42,
                "sample_unit": "rows",
                "minimum_samples": 100,
                "thresholds": {"warn": {"operator": "below", "limit": 100.0}},
                "evidence_count": 2,
                "evidence_truncated": True,
            },
        ),
        DagsterMeasurementMetadataTestCase(
            "warning measurement metadata",
            "warn",
            False,
            {
                "evaluation_mode": "measurement",
                "measured_value": 99.5,
                "sample_count": 100,
                "sample_unit": "rows",
                "minimum_samples": 100,
                "thresholds": {"warn": {"operator": "below", "limit": 100.0}},
            },
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_measurement_check_when_projecting_then_dagster_metadata_and_warning_are_retained(
    test_case: DagsterMeasurementMetadataTestCase,
) -> None:
    envelope: IntegrationResultEnvelope = build_check_integration_envelope(
        check_id="audit:not_null:model:orders:order_id",
        name="not_null",
        event_id="event-measurement",
        attempt_id="attempt-measurement",
        event_sequence=5,
    )
    check: IntegrationCheckResult = replace(
        envelope.checks[0],
        status=test_case.expected_status,
        passed=test_case.expected_passed,
        **test_case.expected_metadata,
    )
    envelope = replace(envelope, checks=(check,))

    results: tuple[Any, ...] = _build_results_from_integration_result(
        dg=dg,
        dag=build_dagster_test_dag(),
        envelope=envelope,
        command=("sqb", "audit"),
        context=type("AuditContext", (), {"selected_asset_keys": set()})(),
        emitted_asset_paths={("analytics", "orders")},
    )

    assert len(results) == 1
    result: Any = results[0]
    assert result.passed is test_case.expected_passed
    assert result.severity == dg.AssetCheckSeverity.WARN
    assert result.metadata["status"].value == test_case.expected_status
    for key, expected_value in test_case.expected_metadata.items():
        assert result.metadata[key].value == expected_value


@pytest.mark.parametrize(
    "test_case",
    (DagsterSelectedCheckTestCase("model envelope does not synthesize sources", "", False),),
    ids=lambda case: case.description,
)
def test_given_model_live_envelope_when_projecting_then_only_canonical_asset_is_routed(
    test_case: DagsterSelectedCheckTestCase,
) -> None:
    envelope: IntegrationResultEnvelope = IntegrationResultEnvelope.from_json(
        json.dumps(
            integration_result_payload(
                command="build",
                asset={"kind": "model", "name": "orders", "status": "success"},
            )
        )
    )

    results: tuple[Any, ...] = _build_results_from_integration_result(
        dg=dg,
        dag=build_dagster_test_dag(),
        envelope=envelope,
        command=("sqb", "build"),
        context=type("AssetContext", (), {"selected_asset_keys": set()})(),
        emitted_asset_paths=set(),
    )

    assert tuple(tuple(result.asset_key.path) for result in results) == (("analytics", "orders"),)
    assert test_case.expected_output_path_retained is False


@pytest.mark.parametrize(
    "test_case",
    (DagsterSelectedCheckTestCase("selected seed emits once", "waffle_types", False),),
    ids=lambda case: case.description,
)
def test_given_seed_live_and_final_results_when_deduplicating_then_selected_seed_emits_once(
    test_case: DagsterSelectedCheckTestCase,
) -> None:
    dag: Mapping[str, Any] = build_dagster_test_dag()
    context: Any = type(
        "SeedContext",
        (),
        {"selected_asset_keys": {dg.AssetKey(["analytics", "waffle_types"])}},
    )()
    envelope: IntegrationResultEnvelope = IntegrationResultEnvelope.from_json(
        json.dumps(
            integration_result_payload(
                command="seed",
                asset={"kind": "seed", "name": "waffle_types", "status": "success"},
            )
        )
    )
    emitted: set[tuple[str, ...]] = set()
    live_results: tuple[Any, ...] = _build_results_from_integration_result(
        dg=dg,
        dag=dag,
        envelope=envelope,
        command=("sqb", "seed"),
        context=context,
        emitted_asset_paths=emitted,
    )
    for result in live_results:
        emitted.add(tuple(result.asset_key.path))
    final_results: tuple[Any, ...] = _build_results_from_execution_payload(
        dg=dg,
        dag=dag,
        payload={
            "version": 1,
            "command": "seed",
            "assets": ({"kind": "seed", "name": "waffle_types", "status": "success"},),
            "checks": (),
        },
        command=("sqb", "seed"),
        context=context,
    )
    final_keys: tuple[tuple[str, ...], ...] = tuple(
        tuple(result.asset_key.path) for result in final_results
    )

    assert tuple(tuple(result.asset_key.path) for result in live_results) == (
        ("analytics", "waffle_types"),
    )
    assert final_keys == tuple(emitted)
    assert test_case.expected_check_name == "waffle_types"
    assert test_case.expected_output_path_retained is False


@pytest.mark.parametrize(
    "test_case",
    (DagsterFutureCursorMetadataTestCase("maximum-start cap metadata", "cap"),),
    ids=lambda case: case.description,
)
def test_given_maximum_start_capping_when_projecting_live_model_then_dagster_matches_final_schema(
    test_case: DagsterFutureCursorMetadataTestCase,
) -> None:
    safety: dict[str, object] | None = serialize_maximum_start_safety(
        MaximumStartSafetyEvidence(
            action=FutureCursorAction.CAP,
            max_ahead="0d",
            invocation_time="2026-09-02T12:00:00+00:00",
            physical_target_max="2026-09-03",
            highest_eligible_target_max="2026-09-02",
            effective_start="2026-09-02",
            maximum_allowed_start="2026-09-02",
            target_relation="analytics.orders",
            cursor_column="order_date",
        )
    )
    assert safety is not None
    envelope: IntegrationResultEnvelope = IntegrationResultEnvelope.from_json(
        json.dumps(
            integration_result_payload(
                command="build",
                asset={
                    "kind": "model",
                    "name": "orders",
                    "status": "success",
                    "maximum_start_safety": safety,
                },
            )
        )
    )

    results: tuple[Any, ...] = _build_results_from_integration_result(
        dg=dg,
        dag=build_dagster_test_dag(),
        envelope=envelope,
        command=("sqb", "build"),
        context=type("AssetContext", (), {"selected_asset_keys": set()})(),
        emitted_asset_paths={("raw", "orders"), ("analytics", "normalize_email")},
    )

    assert results[0].metadata["maximum_start_safety"] == safety
    assert results[0].metadata["maximum_start_safety"]["action"] == test_case.expected_action


@pytest.mark.parametrize(
    "test_case",
    (DagsterSelectedCheckTestCase("malformed live record logs bounded warning", "", False),),
    ids=lambda case: case.description,
)
def test_given_malformed_complete_live_record_when_parsing_then_warning_omits_record_contents(
    test_case: DagsterSelectedCheckTestCase, tmp_path: Path
) -> None:
    logger: Mock = Mock()
    context: Any = type("WarningContext", (), {"log": logger})()
    invocation: SqlBuildCliInvocation = SqlBuildCliInvocation(
        process=Mock(),
        command=("sqb", "build"),
        project_dir=tmp_path,
        context=context,
    )

    results: list[Any] = list(
        invocation._results_from_live_event_line(
            dg=dg,
            dag=build_dagster_test_dag(),
            line='{"schema_version":"secret-line-content"}',
            logged_failed_assets=set(),
            emitted_asset_keys=set(),
        )
    )

    assert results == []
    logger.warning.assert_called_once_with("Ignored invalid SQLBuild integration result record")
    assert "secret-line-content" not in str(logger.warning.call_args)
    assert test_case.expected_output_path_retained is False


@pytest.mark.parametrize(
    "test_case",
    (DagsterFutureCursorMetadataTestCase("unknown optional microbatch action", "future_action"),),
    ids=lambda case: case.description,
)
def test_given_unknown_optional_action_when_parsing_live_record_then_asset_stream_continues(
    test_case: DagsterFutureCursorMetadataTestCase, tmp_path: Path
) -> None:
    logger: Mock = Mock()
    invocation: SqlBuildCliInvocation = SqlBuildCliInvocation(
        process=Mock(),
        command=("sqb", "build"),
        project_dir=tmp_path,
        context=type("AssetContext", (), {"selected_asset_keys": set(), "log": logger})(),
    )
    line: str = json.dumps(
        integration_result_payload(
            command="build",
            asset={
                "kind": "model",
                "name": "orders",
                "status": "success",
                "microbatch": {"action": test_case.expected_action, "limit": 2},
            },
        )
    )

    results: list[Any] = list(
        invocation._results_from_live_event_line(
            dg=dg,
            dag=build_dagster_test_dag(),
            line=line,
            logged_failed_assets=set(),
            emitted_asset_keys=set(),
        )
    )

    assert tuple(tuple(result.asset_key.path) for result in results) == (("analytics", "orders"),)
    assert results[0].metadata["microbatch"] == {"limit": 2}
    logger.warning.assert_not_called()


@pytest.mark.parametrize(
    "test_case",
    (
        DagsterSelectedCheckTestCase(
            "json stdout selects one attachment", "audit__unique__order_id", False
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_json_stdout_with_two_checks_when_one_check_selected_then_only_selected_check_yields(
    test_case: DagsterSelectedCheckTestCase, tmp_path: Path
) -> None:
    project_dir: Path = tmp_path / "project"
    project_dir.mkdir()
    dag: dict[str, Any] = dict(build_dagster_test_dag())
    dag["checks"] = [
        *dag["checks"],
        {
            "id": "audit:unique:model:orders:order_id",
            "kind": "audit",
            "name": "unique",
            "checked_asset_ids": ["model:orders"],
            "attached_column_name": "order_id",
        },
    ]
    dag_path: Path = tmp_path / "dag.json"
    dag_path.write_text(json.dumps(dag), encoding="utf-8")
    payload: str = json.dumps(
        {
            "version": 1,
            "command": "build",
            "status": "success",
            "summary": {},
            "assets": [],
            "checks": [
                {
                    "kind": "audit",
                    "name": "not_null",
                    "check_id": "audit:not_null:model:orders:order_id",
                    "passed": True,
                    "status": "pass",
                },
                {
                    "kind": "audit",
                    "name": "unique",
                    "check_id": "audit:unique:model:orders:order_id",
                    "passed": True,
                    "status": "pass",
                },
            ],
        }
    )
    selected_key: Any = dg.AssetCheckKey(
        asset_key=dg.AssetKey(["analytics", "orders"]),
        name=test_case.expected_check_name,
    )
    context: Any = type(
        "SelectedCheckContext",
        (),
        {"selected_asset_keys": set(), "selected_asset_check_keys": {selected_key}},
    )()
    resource: SqlBuildCliResource = SqlBuildCliResource(
        project_dir=str(project_dir),
        sqb_command=write_fake_sqb_command(root=tmp_path, stdout=payload),
        dag_path=str(dag_path),
    )

    results: list[Any] = list(resource.cli(args=["build", "--json"], context=context).stream())

    assert [result.check_name for result in results] == [test_case.expected_check_name]


@pytest.mark.parametrize(
    "test_case",
    (DagsterSelectedCheckTestCase("caller json output is retained", "", True),),
    ids=lambda case: case.description,
)
def test_given_caller_json_output_path_when_streaming_then_payload_is_loaded_without_deleting_file(
    test_case: DagsterSelectedCheckTestCase, tmp_path: Path
) -> None:
    project_dir: Path = tmp_path / "project"
    project_dir.mkdir()
    output_path: Path = tmp_path / "caller.json"
    payload: str = json.dumps(
        {
            "version": 1,
            "command": "build",
            "status": "success",
            "summary": {},
            "assets": [{"kind": "model", "name": "customers", "status": "success"}],
            "checks": [],
        }
    )
    resource: SqlBuildCliResource = SqlBuildCliResource(
        project_dir=str(project_dir),
        sqb_command=write_fake_sqb_command(root=tmp_path, stdout=payload),
        dag_path=str(write_dagster_test_dag(root=tmp_path)),
    )
    context: Any = type("CallerOutputContext", (), {"selected_asset_keys": set()})()

    results: list[Any] = list(
        resource.cli(args=["build", "--json-output", str(output_path)], context=context).stream()
    )

    assert tuple(results[0].asset_key.path) == ("analytics", "customers")
    assert output_path.exists() is test_case.expected_output_path_retained


@pytest.mark.parametrize(
    "test_case",
    (DagsterSelectedCheckTestCase("caller equals json output is retained", "", True),),
    ids=lambda case: case.description,
)
def test_given_equals_json_output_path_when_streaming_then_option_is_not_duplicated_and_file_remains(
    test_case: DagsterSelectedCheckTestCase, tmp_path: Path
) -> None:
    project_dir: Path = tmp_path / "project"
    project_dir.mkdir()
    output_path: Path = tmp_path / "caller-equals.json"
    payload: str = json.dumps(
        {
            "version": 1,
            "command": "build",
            "status": "success",
            "summary": {},
            "assets": [{"kind": "model", "name": "customers", "status": "success"}],
            "checks": [],
        }
    )
    resource: SqlBuildCliResource = SqlBuildCliResource(
        project_dir=str(project_dir),
        sqb_command=write_fake_sqb_command(root=tmp_path, stdout=payload),
        dag_path=str(write_dagster_test_dag(root=tmp_path)),
    )
    context: Any = type("EqualsOutputContext", (), {"selected_asset_keys": set()})()

    invocation: SqlBuildCliInvocation = resource.cli(
        args=["build", f"--json-output={output_path}"], context=context
    )
    results: list[Any] = list(invocation.stream())

    assert invocation.command.count("--json-output") == 0
    assert invocation.command.count(f"--json-output={output_path}") == 1
    assert tuple(results[0].asset_key.path) == ("analytics", "customers")
    assert output_path.exists() is test_case.expected_output_path_retained


@pytest.mark.parametrize(
    "test_case",
    [
        DagsterCliInvocationTestCase(
            description="wait captures successful command output",
            command_stdout="built ok\n",
            command_stderr="warning line\n",
            command_exit_code=0,
            expected_success=True,
            expected_stdout="built ok\n",
            expected_stderr="warning line\n",
        ),
        DagsterCliInvocationTestCase(
            description="wait captures failing command output without raising when disabled",
            command_stdout="",
            command_stderr="boom\n",
            command_exit_code=7,
            expected_success=False,
            expected_stdout="",
            expected_stderr="boom\n",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_sqlbuild_cli_resource_when_waiting_invocation_then_captures_process_result(
    test_case: DagsterCliInvocationTestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = tmp_path / "project"
    project_dir.mkdir()
    resource: SqlBuildCliResource = SqlBuildCliResource(
        project_dir=str(project_dir),
        sqb_command=write_fake_sqb_command(
            root=tmp_path,
            stdout=test_case.command_stdout,
            stderr=test_case.command_stderr,
            exit_code=test_case.command_exit_code,
        ),
    )

    invocation: SqlBuildCliInvocation = resource.cli(["build"], raise_on_error=False).wait()

    assert invocation.is_successful() is test_case.expected_success
    assert invocation.stdout == test_case.expected_stdout
    assert invocation.stderr == test_case.expected_stderr


@pytest.mark.parametrize(
    "test_case",
    [
        DagsterCliLiveLogTestCase(
            description="unflushed subprocess output reaches Dagster before process completion",
            expected_stdout_lines=("started without explicit flush", "completed"),
            expected_stderr_lines=("warning without explicit flush",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_running_sqlbuild_command_when_output_arrives_then_only_compute_streams_receive_it(
    test_case: DagsterCliLiveLogTestCase,
    tmp_path: Path,
    capfd: pytest.CaptureFixture[str],
) -> None:
    project_dir: Path = tmp_path / "project"
    project_dir.mkdir()
    release_path: Path = tmp_path / "release"
    logger: Mock = Mock()
    context: Any = type("LoggingContext", (), {"log": logger})()
    resource: SqlBuildCliResource = SqlBuildCliResource(
        project_dir=str(project_dir),
        sqb_command=write_blocking_fake_sqb_command(
            root=tmp_path,
            release_path=release_path,
        ),
    )
    invocation: SqlBuildCliInvocation = resource.cli(
        ["build"], context=context, raise_on_error=False
    )

    release_path.write_text("continue", encoding="utf-8")
    completed_invocation: SqlBuildCliInvocation = invocation.wait()
    captured: CaptureResult[str] = capfd.readouterr()

    for line in test_case.expected_stdout_lines:
        assert line in captured.out
    for line in test_case.expected_stderr_lines:
        assert line in captured.err
    assert not logger.info.called
    assert not logger.warning.called
    assert completed_invocation.stdout == "".join(
        f"{line}\n" for line in test_case.expected_stdout_lines
    )
    assert completed_invocation.stderr == "".join(
        f"{line}\n" for line in test_case.expected_stderr_lines
    )


@pytest.mark.parametrize(
    "test_case",
    (
        DagsterCliLiveLogTestCase(
            description="verbose SQL stays in compute stdout instead of Dagster event logs",
            expected_stdout_lines=("    SELECT * FROM orders",),
            expected_stderr_lines=(),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_verbose_command_when_streaming_output_then_keeps_sql_out_of_context_log(
    test_case: DagsterCliLiveLogTestCase, tmp_path: Path
) -> None:
    project_dir: Path = tmp_path / "project"
    project_dir.mkdir()
    logger: Mock = Mock()
    invocation: SqlBuildCliInvocation = SqlBuildCliResource(
        project_dir=str(project_dir),
        sqb_command=write_fake_sqb_command(
            root=tmp_path,
            stdout="".join(f"{line}\n" for line in test_case.expected_stdout_lines),
        ),
    ).cli(
        ["build", "--verbose"],
        context=type("VerboseContext", (), {"log": logger})(),
        raise_on_error=False,
    )

    invocation.wait()

    assert invocation.stdout == "".join(f"{line}\n" for line in test_case.expected_stdout_lines)
    assert not any(
        call.args and call.args[0] == "SQLBuild: %s" for call in logger.info.call_args_list
    )


@pytest.mark.parametrize(
    "test_case",
    [
        DagsterCliStreamTestCase(
            description="stream yields materialize results for dag assets",
            command_stdout="built ok\n",
            command_exit_code=0,
            expected_asset_keys=(
                ("shared_order_feed",),
                ("analytics", "waffle_types"),
                ("analytics", "normalize_email"),
                ("analytics", "customers"),
                ("raw_orders_loader",),
                ("raw", "orders"),
                ("analytics", "orders"),
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_sqlbuild_cli_resource_with_dag_when_streaming_then_yields_asset_results(
    test_case: DagsterCliStreamTestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = tmp_path / "project"
    project_dir.mkdir()
    resource: SqlBuildCliResource = SqlBuildCliResource(
        project_dir=str(project_dir),
        sqb_command=write_fake_sqb_command(
            root=tmp_path,
            stdout=test_case.command_stdout,
            exit_code=test_case.command_exit_code,
        ),
        dag_path=str(write_dagster_test_dag(root=tmp_path)),
    )

    results: list[Any] = list(resource.cli(args=["build"]).stream())

    assert (
        tuple(tuple(result.asset_key.path) for result in results) == test_case.expected_asset_keys
    )


@pytest.mark.parametrize(
    "test_case",
    [
        DagsterCliJsonStreamTestCase(
            description="stream yields execution json asset and check results",
            command_stdout=(
                '{"version": 1, "command": "build", "status": "success", '
                '"summary": {}, '
                '"assets": [{"kind": "model", "name": "orders", '
                '"status": "success", "duration_ms": 12}], '
                '"checks": [{"kind": "audit", "name": "not_null", '
                '"check_id": "audit:not_null:model:orders:order_id", '
                '"passed": true, "status": "pass", "severity": "warn", '
                '"row_count": 0}]}'
            ),
            selected_asset_keys=(("analytics", "orders"),),
            expected_asset_keys=(("analytics", "orders"),),
            expected_check_names=("audit__not_null__order_id",),
            expected_check_severities=("WARN",),
        ),
        DagsterCliJsonStreamTestCase(
            description="check-only selection emits only selected audit result",
            command_stdout=(
                '{"version": 1, "command": "build", "status": "success", '
                '"summary": {}, '
                '"assets": [{"kind": "model", "name": "orders", '
                '"status": "success", "duration_ms": 12}], '
                '"checks": [{"kind": "audit", "name": "not_null", '
                '"check_id": "audit:not_null:model:orders:order_id", '
                '"passed": true, "status": "pass", "severity": "warn", '
                '"row_count": 0}, '
                '{"kind": "audit", "name": "freshness", '
                '"check_id": "audit:freshness:source:raw_orders:loaded_at", '
                '"passed": true, "status": "pass", "severity": "warn", '
                '"row_count": 0}]} '
            ),
            selected_asset_keys=(),
            selected_check_keys=((("analytics", "orders"), "audit__not_null__order_id"),),
            check_selection_is_explicit=True,
            expected_asset_keys=(),
            expected_check_names=("audit__not_null__order_id",),
            expected_check_severities=("WARN",),
        ),
        DagsterCliJsonStreamTestCase(
            description="combined selection retains check outside selected asset paths",
            command_stdout=(
                '{"version": 1, "command": "build", "status": "success", '
                '"summary": {}, '
                '"assets": [{"kind": "model", "name": "orders", "status": "success"}], '
                '"checks": [{"kind": "audit", "name": "not_null", '
                '"check_id": "audit:not_null:model:orders:order_id", '
                '"passed": true, "status": "pass", "severity": "warn"}]}'
            ),
            selected_asset_keys=(("analytics", "customers"),),
            selected_check_keys=((("analytics", "orders"), "audit__not_null__order_id"),),
            check_selection_is_explicit=True,
            expected_asset_keys=(),
            expected_check_names=("audit__not_null__order_id",),
            expected_check_severities=("WARN",),
        ),
        DagsterCliJsonStreamTestCase(
            description="explicit empty check selection suppresses audit results",
            command_stdout=(
                '{"version": 1, "command": "build", "status": "success", '
                '"summary": {}, '
                '"assets": [{"kind": "model", "name": "orders", "status": "success"}], '
                '"checks": [{"kind": "audit", "name": "not_null", '
                '"check_id": "audit:not_null:model:orders:order_id", '
                '"passed": true, "status": "pass", "severity": "warn"}]}'
            ),
            selected_asset_keys=(("analytics", "orders"),),
            check_selection_is_explicit=True,
            expected_asset_keys=(("analytics", "orders"),),
            expected_check_names=(),
            expected_check_severities=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_execution_json_when_streaming_then_yields_structured_dagster_events(
    test_case: DagsterCliJsonStreamTestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = tmp_path / "project"
    project_dir.mkdir()
    context: Any = type(
        "SelectedAssetContext",
        (),
        {
            "selected_asset_keys": {
                dg.AssetKey(list(asset_key)) for asset_key in test_case.selected_asset_keys
            },
            "selected_asset_check_keys": (
                None,
                {
                    dg.AssetCheckKey(asset_key=dg.AssetKey(list(asset_key)), name=check_name)
                    for asset_key, check_name in test_case.selected_check_keys
                },
            )[test_case.check_selection_is_explicit],
        },
    )()
    resource: SqlBuildCliResource = SqlBuildCliResource(
        project_dir=str(project_dir),
        sqb_command=write_fake_sqb_command(root=tmp_path, stdout=test_case.command_stdout),
        dag_path=str(write_dagster_test_dag(root=tmp_path)),
    )

    results: list[Any] = list(resource.cli(args=["build"], context=context).stream())

    materialize_results_by_status: defaultdict[bool, list[Any]] = defaultdict(list)
    check_results_by_status: defaultdict[bool, list[Any]] = defaultdict(list)
    for result in results:
        materialize_results_by_status[isinstance(result, dg.MaterializeResult)].append(result)
        check_results_by_status[isinstance(result, dg.AssetCheckResult)].append(result)
    materialize_results: list[Any] = materialize_results_by_status[True]
    check_results: list[Any] = check_results_by_status[True]
    assert tuple(tuple(result.asset_key.path) for result in materialize_results) == (
        test_case.expected_asset_keys
    )
    assert tuple(result.check_name for result in check_results) == test_case.expected_check_names
    assert tuple(result.severity.value for result in check_results) == (
        test_case.expected_check_severities
    )


@pytest.mark.parametrize(
    "test_case",
    (
        DagsterTranslatorRuntimeTestCase(
            description="custom asset and check identities remain consistent at runtime",
            payload=(
                '{"version": 1, "command": "build", "status": "success", '
                '"summary": {}, "assets": ['
                '{"kind": "source", "name": "raw_orders", "status": "success"}, '
                '{"kind": "model", "name": "orders", "status": "success"}], '
                '"checks": [{"kind": "audit", "name": "not_null", '
                '"check_id": "audit:not_null:model:orders:order_id", '
                '"passed": true, "status": "pass", "severity": "error"}]}'
            ),
            selected_asset_key=("translated", "orders"),
            expected_selection=("orders",),
            expected_asset_keys=(("translated", "orders"),),
            expected_check_names=("translated__not_null",),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_custom_translator_when_selecting_and_streaming_then_runtime_uses_translated_identities(
    test_case: DagsterTranslatorRuntimeTestCase,
    tmp_path: Path,
) -> None:
    context: Any = type(
        "TranslatedAssetContext",
        (),
        {
            "selected_asset_keys": {dg.AssetKey(test_case.selected_asset_key)},
            "selected_asset_check_keys": None,
        },
    )()
    project_dir: Path = tmp_path / "project"
    project_dir.mkdir()
    resource: SqlBuildCliResource = SqlBuildCliResource(
        project_dir=project_dir,
        sqb_command=write_fake_sqb_command(root=tmp_path, stdout=test_case.payload),
        dag_path=write_dagster_test_dag(root=tmp_path),
    )

    invocation: SqlBuildCliInvocation = resource.cli(
        args=["build"],
        context=context,
        translator=_NamespacedDagsterTranslator(),
    )
    results: list[Any] = list(invocation.stream())

    results_by_materialization_status: defaultdict[bool, list[Any]] = defaultdict(list)
    results_by_check_status: defaultdict[bool, list[Any]] = defaultdict(list)
    for result in results:
        results_by_materialization_status[isinstance(result, dg.MaterializeResult)].append(result)
        results_by_check_status[isinstance(result, dg.AssetCheckResult)].append(result)

    assert invocation.selection == test_case.expected_selection
    assert (
        tuple(tuple(result.asset_key.path) for result in results_by_materialization_status[True])
        == test_case.expected_asset_keys
    )
    assert (
        tuple(result.check_name for result in results_by_check_status[True])
        == test_case.expected_check_names
    )


@pytest.mark.parametrize(
    "test_case",
    [DagsterFutureCursorMetadataTestCase("future cursor metadata", "cap")],
    ids=lambda case: case.description,
)
def test_given_future_cursor_execution_metadata_when_streaming_then_dagster_retains_structure(
    test_case: DagsterFutureCursorMetadataTestCase, tmp_path: Path
) -> None:
    project_dir: Path = tmp_path / "project"
    project_dir.mkdir()
    safety: dict[str, object] = {
        "action": "cap",
        "max_distance": "2d",
        "discovered_bounds": {"start": "2500-01-01", "end": "2500-01-02"},
        "applied_bounds": {"start": "2500-01-01", "end": "2026-09-04"},
        "determining_input": {
            "relation": "raw.events",
            "cursor_column": "occurred_at",
        },
        "inputs": [
            {
                "relation": "raw.events",
                "cursor_column": "occurred_at",
                "minimum": None,
                "maximum": "2500-01-01",
            }
        ],
    }
    stdout: str = json.dumps(
        {
            "version": 1,
            "command": "build",
            "status": "success",
            "summary": {},
            "assets": [
                {
                    "kind": "model",
                    "name": "orders",
                    "status": "success",
                    "future_cursor_safety": safety,
                }
            ],
            "checks": [],
        }
    )
    context: Any = type(
        "SelectedAssetContext",
        (),
        {"selected_asset_keys": {dg.AssetKey(["analytics", "orders"])}},
    )()
    resource: SqlBuildCliResource = SqlBuildCliResource(
        project_dir=str(project_dir),
        sqb_command=write_fake_sqb_command(root=tmp_path, stdout=stdout),
        dag_path=str(write_dagster_test_dag(root=tmp_path)),
    )

    results: list[Any] = list(resource.cli(args=["build"], context=context).stream())

    materialization: Any = results[0]
    assert materialization.metadata["future_cursor_safety"] == safety
    assert materialization.metadata["future_cursor_safety"]["action"] == test_case.expected_action


@pytest.mark.parametrize(
    "test_case",
    [
        DagsterMicrobatchLimitMetadataTestCase(
            description=f"canonical microbatch action {action.value}",
            execution_status="success",
            expected_microbatch={
                "run_type": "normal",
                "limit": 2,
                "count": 3,
                "action": action.value,
            },
        )
        for action in MicrobatchLimitAction
    ],
    ids=lambda case: case.description,
)
def test_given_microbatch_limit_execution_metadata_when_streaming_then_dagster_retains_structure(
    test_case: DagsterMicrobatchLimitMetadataTestCase, tmp_path: Path
) -> None:
    project_dir: Path = tmp_path / "project"
    project_dir.mkdir()
    stdout: str = json.dumps(
        {
            "version": 1,
            "command": "build",
            "status": "success",
            "summary": {},
            "assets": [
                {
                    "kind": "model",
                    "name": "orders",
                    "status": test_case.execution_status,
                    "microbatch": test_case.expected_microbatch,
                }
            ],
            "checks": [],
        }
    )
    context: Any = type(
        "SelectedAssetContext",
        (),
        {"selected_asset_keys": {dg.AssetKey(["analytics", "orders"])}},
    )()
    resource: SqlBuildCliResource = SqlBuildCliResource(
        project_dir=str(project_dir),
        sqb_command=write_fake_sqb_command(root=tmp_path, stdout=stdout),
        dag_path=str(write_dagster_test_dag(root=tmp_path)),
    )

    results: list[Any] = list(resource.cli(args=["build"], context=context).stream())

    materialization: Any = results[0]
    assert materialization.metadata["microbatch"] == test_case.expected_microbatch


@pytest.mark.parametrize(
    "test_case",
    [
        DagsterMicrobatchLimitMetadataTestCase(
            description="warn limit metadata after failed pre-hook",
            execution_status="failed",
            expected_microbatch={
                "run_type": "normal",
                "limit": 2,
                "count": 3,
                "action": "warn",
                "warning": "MICROBATCH LIMIT EXCEEDED",
            },
        )
    ],
    ids=lambda case: case.description,
)
def test_given_warn_limit_metadata_when_cli_fails_then_dagster_failure_retains_evidence(
    test_case: DagsterMicrobatchLimitMetadataTestCase, tmp_path: Path
) -> None:
    project_dir: Path = tmp_path / "project"
    project_dir.mkdir()
    stdout: str = json.dumps(
        {
            "version": 1,
            "command": "build",
            "status": "failed",
            "summary": {},
            "assets": [
                {
                    "kind": "model",
                    "name": "orders",
                    "status": test_case.execution_status,
                    "failed_phase": "pre_hook",
                    "microbatch": test_case.expected_microbatch,
                }
            ],
            "checks": [],
        }
    )
    resource: SqlBuildCliResource = SqlBuildCliResource(
        project_dir=str(project_dir),
        sqb_command=write_fake_sqb_command(root=tmp_path, stdout=stdout, exit_code=1),
        dag_path=str(write_dagster_test_dag(root=tmp_path)),
    )

    with pytest.raises(dg.Failure) as exc_info:
        list(resource.cli(args=["build"]).stream())

    assert exc_info.value.metadata["microbatch_limits"].value == {
        "orders": test_case.expected_microbatch
    }


@pytest.mark.parametrize(
    "test_case",
    [
        DagsterCliCloneStreamTestCase(
            description="clone execution yields materializations for successful items only",
            command_stdout=(
                '{"version": 1, "command": "clone", "status": "success", '
                '"summary": {"success_count": 2}, '
                '"assets": [{"kind": "model", "name": "orders", '
                '"status": "success", "action": "cloned"}, '
                '{"kind": "seed", "name": "waffle_types", '
                '"status": "success", "action": "copied"}], "checks": []}'
            ),
            expected_asset_keys=(("analytics", "waffle_types"), ("analytics", "orders")),
            expected_actions=("copied", "cloned"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_clone_execution_json_when_streaming_then_yields_asset_materializations(
    test_case: DagsterCliCloneStreamTestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = tmp_path / "project"
    project_dir.mkdir()
    context: Any = type(
        "AggregateCloneContext",
        (),
        {"selected_asset_keys": {dg.AssetKey(["aggregate_clone"])}},
    )()
    resource: SqlBuildCliResource = SqlBuildCliResource(
        project_dir=str(project_dir),
        sqb_command=write_fake_sqb_command(root=tmp_path, stdout=test_case.command_stdout),
        dag_path=str(write_dagster_test_dag(root=tmp_path)),
    )

    results: list[Any] = list(
        resource.cli(args=["clone", "--from", "prod"], context=context).stream()
    )

    assert all(isinstance(result, dg.AssetMaterialization) for result in results)
    assert (
        tuple(tuple(result.asset_key.path) for result in results) == test_case.expected_asset_keys
    )
    assert (
        tuple(result.metadata["action"].value for result in results) == test_case.expected_actions
    )


@pytest.mark.parametrize(
    "test_case",
    (
        DagsterCliLiveCloneEventTestCase(
            description="completed clone item materializes while subprocess remains blocked",
            command="clone",
            command_args=("clone", "--from", "prod"),
            expected_asset_key=("analytics", "customers"),
        ),
        DagsterCliLiveCloneEventTestCase(
            description="build item with reused parents materializes while subprocess remains blocked",
            command="build",
            command_args=("build",),
            expected_asset_key=("analytics", "orders"),
        ),
        DagsterCliLiveCloneEventTestCase(
            description="partial JSONL writes are buffered until their record is complete",
            command="build",
            command_args=("build",),
            expected_asset_key=("analytics", "customers"),
        ),
        DagsterCliLiveCloneEventTestCase(
            description="run uses the shared live execution event transport",
            command="run",
            command_args=("run",),
            expected_asset_key=("analytics", "customers"),
        ),
        DagsterCliLiveCloneEventTestCase(
            description="test uses the shared live execution event transport",
            command="test",
            command_args=("test",),
            expected_asset_key=("analytics", "customers"),
        ),
        DagsterCliLiveCloneEventTestCase(
            description="check uses the shared live execution event transport",
            command="check",
            command_args=("check",),
            expected_asset_key=("analytics", "customers"),
        ),
        DagsterCliLiveCloneEventTestCase(
            description="audit uses the shared live execution event transport",
            command="audit",
            command_args=("audit",),
            expected_asset_key=("analytics", "customers"),
        ),
        DagsterCliLiveCloneEventTestCase(
            description="seed uses the shared live execution event transport",
            command="seed",
            command_args=("seed",),
            expected_asset_key=("analytics", "customers"),
        ),
        DagsterCliLiveCloneEventTestCase(
            description="load uses the shared live execution event transport",
            command="load",
            command_args=("load",),
            expected_asset_key=("analytics", "customers"),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_running_clone_when_item_completes_then_materializes_before_process_exit(
    test_case: DagsterCliLiveCloneEventTestCase, tmp_path: Path
) -> None:
    project_dir: Path = tmp_path / "project"
    project_dir.mkdir()
    release_path: Path = tmp_path / "release"
    context: Any = type("AggregateCloneContext", (), {"selected_asset_keys": set()})()
    resource: SqlBuildCliResource = SqlBuildCliResource(
        project_dir=str(project_dir),
        sqb_command=write_blocking_execution_event_command(
            root=tmp_path,
            release_path=release_path,
            command=test_case.command,
            asset_name=test_case.expected_asset_key[-1],
        ),
        dag_path=str(write_dagster_test_dag(root=tmp_path)),
    )
    invocation: SqlBuildCliInvocation = resource.cli(args=test_case.command_args, context=context)
    stream: Iterator[Any] = invocation.stream()

    materialization: Any = next(stream)

    assert invocation.process.poll() is None
    release_path.touch()
    remaining_results: list[Any] = list(stream)
    assert (
        tuple(materialization.asset_key.path),
        *(tuple(result.asset_key.path) for result in remaining_results),
    ) == (
        test_case.expected_asset_key,
        *test_case.expected_remaining_asset_keys,
    )
    assert invocation.returncode == 0


@pytest.mark.parametrize(
    "test_case",
    [
        DagsterLiveFailureLoggingTestCase(
            "live failed asset logging",
            "staging",
            "R002",
            "SQLBuild resource attempt failed; see final execution diagnostics",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_live_failed_asset_when_event_arrives_then_logs_error_before_process_exit(
    test_case: DagsterLiveFailureLoggingTestCase, tmp_path: Path
) -> None:
    project_dir: Path = tmp_path / "project"
    project_dir.mkdir()
    release_path: Path = tmp_path / "release"
    error_received: Event = Event()
    logger: Mock = Mock()
    logger.error.side_effect = lambda *_args, **_kwargs: error_received.set()
    context: Any = type(
        "FailedAssetContext",
        (),
        {"log": logger, "selected_asset_keys": set()},
    )()
    invocation: SqlBuildCliInvocation = SqlBuildCliResource(
        project_dir=str(project_dir),
        sqb_command=write_blocking_failed_execution_event_command(
            root=tmp_path,
            release_path=release_path,
        ),
        dag_path=str(write_dagster_test_dag(root=tmp_path)),
    ).cli(args=["build"], context=context, raise_on_error=False)
    expected_command: str = " ".join(invocation.command)

    with ThreadPoolExecutor(max_workers=1) as executor:
        stream_future: Future[list[Any]] = executor.submit(lambda: list(invocation.stream()))
        assert error_received.wait(timeout=3)
        assert not stream_future.done()
        release_path.touch()
        stream_future.result(timeout=3)

    logger.error.assert_called_once()
    log_call: Any = logger.error.call_args
    assert log_call.args == (
        "SQLBuild asset failed: asset=%s phase=%s code=%s message=%s",
        "model:customers",
        test_case.expected_phase,
        test_case.expected_error_code,
        test_case.expected_error_message,
    )
    assert log_call.kwargs["extra"] == {
        "sqlbuild_asset": "model:customers",
        "sqlbuild_asset_kind": "model",
        "sqlbuild_asset_name": "customers",
        "sqlbuild_phase": "staging",
        "sqlbuild_error_code": "R002",
        "sqlbuild_error_message": test_case.expected_error_message,
        "sqlbuild_command": expected_command,
        "sqlbuild_staging_relation": "analytics.customers__staging",
        "sqlbuild_duration_ms": 123,
    }


@pytest.mark.parametrize(
    "test_case",
    (
        DagsterCliLiveCloneEventTestCase(
            description="closing a live event stream terminates its blocked subprocess",
            command="build",
            command_args=("build",),
            expected_asset_key=("analytics", "customers"),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_blocked_command_when_live_stream_closes_then_subprocess_terminates(
    test_case: DagsterCliLiveCloneEventTestCase, tmp_path: Path
) -> None:
    project_dir: Path = tmp_path / "project"
    project_dir.mkdir()
    invocation: SqlBuildCliInvocation = SqlBuildCliResource(
        project_dir=str(project_dir),
        sqb_command=write_blocking_execution_event_command(
            root=tmp_path,
            release_path=tmp_path / "never-release",
            command=test_case.command,
        ),
        dag_path=str(write_dagster_test_dag(root=tmp_path)),
    ).cli(
        args=test_case.command_args,
        context=type("LiveEventContext", (), {"selected_asset_keys": set()})(),
    )
    stream: Generator[Any, None, None] = cast(Generator[Any, None, None], invocation.stream())

    materialization: Any = next(stream)
    stream.close()

    assert tuple(materialization.asset_key.path) == test_case.expected_asset_key
    assert invocation.process.wait(timeout=3) is not None


@pytest.mark.parametrize(
    "test_case",
    [
        DagsterCliCloneFailureTestCase(
            description="partial clone failure preserves confirmed materializations",
            command_stdout=(
                '{"version": 1, "command": "clone", "status": "failed", '
                '"summary": {"success_count": 1, "failure_count": 1}, '
                '"assets": [{"kind": "model", "name": "orders", '
                '"status": "success", "action": "cloned"}, '
                '{"kind": "model", "name": "customers", '
                '"status": "failed", "action": "failed", "failed_phase": "staging", '
                '"error_code": "R002", "error_message": "invalid identifier CUSTOMER_ID", '
                '"staging_relation": "analytics.customers__staging"}], "checks": []}'
            ),
            expected_materialized_asset_key=("analytics", "orders"),
            expected_incomplete_assets="model:customers (failed)",
            expected_error_fragments=(
                "model:customers (failed) during staging",
                "[R002] invalid identifier CUSTOMER_ID",
                "staging relation: analytics.customers__staging",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_partial_clone_failure_when_streaming_then_preserves_confirmed_materializations(
    test_case: DagsterCliCloneFailureTestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = tmp_path / "project"
    project_dir.mkdir()
    context: Any = type("CloneContext", (), {"selected_asset_keys": set()})()
    resource: SqlBuildCliResource = SqlBuildCliResource(
        project_dir=str(project_dir),
        sqb_command=write_fake_sqb_command(
            root=tmp_path,
            stdout=test_case.command_stdout,
            exit_code=1,
        ),
        dag_path=str(write_dagster_test_dag(root=tmp_path)),
    )
    stream: Iterator[Any] = resource.cli(args=["clone", "--from", "prod"], context=context).stream()

    materialization: Any = next(stream)
    assert tuple(materialization.asset_key.path) == test_case.expected_materialized_asset_key
    with pytest.raises(dg.Failure) as exc_info:
        next(stream)

    incomplete_assets: Any = exc_info.value.metadata["incomplete_assets"]
    assert incomplete_assets.value == test_case.expected_incomplete_assets
    assert all(fragment in str(exc_info.value) for fragment in test_case.expected_error_fragments)
    assert "stdout" not in exc_info.value.metadata
    assert "stderr" not in exc_info.value.metadata


@pytest.mark.parametrize(
    "test_case",
    [
        DagsterCliFailureTestCase(
            description="clone failure without payload emits no materializations",
            command_stderr="clone crashed\n",
            command_exit_code=1,
            expected_error_fragment="SQLBuild CLI command failed with exit code 1",
            expected_stderr_tail="clone crashed\n",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_clone_failure_without_payload_when_streaming_then_emits_no_materializations(
    test_case: DagsterCliFailureTestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = tmp_path / "project"
    project_dir.mkdir()
    context: Any = type("CloneContext", (), {"selected_asset_keys": set()})()
    resource: SqlBuildCliResource = SqlBuildCliResource(
        project_dir=str(project_dir),
        sqb_command=write_fake_sqb_command(
            root=tmp_path,
            stderr=test_case.command_stderr,
            exit_code=test_case.command_exit_code,
        ),
        dag_path=str(write_dagster_test_dag(root=tmp_path)),
    )

    with pytest.raises(dg.Failure) as exc_info:
        next(resource.cli(args=["clone", "--from", "prod"], context=context).stream())

    assert test_case.expected_error_fragment in str(exc_info.value)


@pytest.mark.parametrize(
    "test_case",
    [
        DagsterCliFailureTestCase(
            description="wait raises Dagster failure for nonzero command",
            command_stderr="discarded" * 1_000 + "build failed\n",
            command_exit_code=3,
            expected_error_fragment="SQLBuild CLI command failed with exit code 3",
            expected_stderr_tail=("discarded" * 1_000 + "build failed\n")[-4_000:],
        )
    ],
    ids=lambda case: case.description,
)
def test_given_sqlbuild_cli_resource_when_waiting_failed_invocation_then_raises_failure(
    test_case: DagsterCliFailureTestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = tmp_path / "project"
    project_dir.mkdir()
    resource: SqlBuildCliResource = SqlBuildCliResource(
        project_dir=str(project_dir),
        sqb_command=write_fake_sqb_command(
            root=tmp_path,
            stderr=test_case.command_stderr,
            exit_code=test_case.command_exit_code,
        ),
    )

    with pytest.raises(dg.Failure) as error:
        resource.cli(args=["build"]).wait()

    assert test_case.expected_error_fragment in str(error.value)
    assert error.value.metadata["stderr_tail"].value == test_case.expected_stderr_tail
    assert "stderr" not in error.value.metadata


@pytest.mark.parametrize(
    "test_case",
    [
        DagsterCliSelectionTestCase(
            description="selected Dagster asset appends SQLBuild selector",
            selected_asset_keys=(("analytics", "orders"),),
            command_args=("build",),
            expected_selectors=("orders",),
            assert_selector_transport=assert_select_file_selector_behavior,
        ),
        DagsterCliSelectionTestCase(
            description="explicit SQLBuild selector is preserved",
            selected_asset_keys=(("analytics", "orders"),),
            command_args=("build", "--select", "manual_selector"),
            expected_selectors=(),
            assert_selector_transport=assert_positional_selector_behavior,
        ),
        DagsterCliSelectionTestCase(
            description="selected Dagster asset appends attached scenario selectors",
            selected_asset_keys=(("analytics", "orders"),),
            command_args=("scenario", "test"),
            expected_selectors=("orders_minimal",),
            assert_selector_transport=assert_positional_selector_behavior,
        ),
        DagsterCliSelectionTestCase(
            description="explicit scenario selector is preserved",
            selected_asset_keys=(("analytics", "orders"),),
            command_args=("scenario", "test", "manual_scenario"),
            expected_selectors=(),
            assert_selector_transport=assert_positional_selector_behavior,
        ),
        DagsterCliSelectionTestCase(
            description="selected loader asset appends load selector",
            selected_asset_keys=(("shared_order_feed",),),
            command_args=("load",),
            expected_selectors=("shared_order_feed",),
            assert_selector_transport=assert_select_file_selector_behavior,
        ),
        DagsterCliSelectionTestCase(
            description="selected model asset is ignored for load selector",
            selected_asset_keys=(("analytics", "orders"),),
            command_args=("load",),
            expected_selectors=(),
            assert_selector_transport=assert_positional_selector_behavior,
        ),
        DagsterCliSelectionTestCase(
            description="selected audit check appends checked model selector",
            selected_asset_keys=(),
            selected_check_keys=((("analytics", "orders"), "audit__not_null__order_id"),),
            command_args=("build",),
            expected_selectors=("orders",),
            assert_selector_transport=assert_select_file_selector_behavior,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_selected_dagster_assets_when_invoking_cli_then_applies_sqlbuild_selectors(
    test_case: DagsterCliSelectionTestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = tmp_path / "project"
    project_dir.mkdir()
    context: Any = type(
        "SelectedAssetContext",
        (),
        {
            "selected_asset_keys": {
                dg.AssetKey(list(asset_key)) for asset_key in test_case.selected_asset_keys
            },
            "selected_asset_check_keys": {
                dg.AssetCheckKey(asset_key=dg.AssetKey(list(asset_key)), name=check_name)
                for asset_key, check_name in test_case.selected_check_keys
            },
        },
    )()
    resource: SqlBuildCliResource = SqlBuildCliResource(
        project_dir=str(project_dir),
        sqb_command=write_fake_sqb_command(root=tmp_path),
        dag_path=str(write_dagster_test_dag(root=tmp_path)),
    )

    invocation: SqlBuildCliInvocation = resource.cli(
        args=test_case.command_args,
        context=context,
    ).wait()

    assert invocation.is_successful()
    assert invocation.selection == test_case.expected_selectors
    test_case.assert_selector_transport(
        command=invocation.command,
        selectors=test_case.expected_selectors,
    )
    assert_json_output_file_behavior(command=invocation.command)


@pytest.mark.parametrize(
    "test_case",
    [
        DagsterCliSelectionTestCase(
            description="selected Python check appends check selector",
            selected_asset_keys=(),
            command_args=("check",),
            expected_selectors=("check_orders_export",),
            assert_selector_transport=assert_select_file_selector_behavior,
            selected_check_keys=(
                (("asset", "orders_export"), "python_check__check_orders_export"),
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_selected_python_check_when_invoking_check_then_selects_check_identity(
    test_case: DagsterCliSelectionTestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = tmp_path / "project"
    project_dir.mkdir()
    context: Any = type(
        "SelectedCheckContext",
        (),
        {
            "selected_asset_keys": set(),
            "selected_asset_check_keys": {
                dg.AssetCheckKey(asset_key=dg.AssetKey(list(asset_key)), name=check_name)
                for asset_key, check_name in test_case.selected_check_keys
            },
        },
    )()
    resource: SqlBuildCliResource = SqlBuildCliResource(
        project_dir=str(project_dir),
        sqb_command=write_fake_sqb_command(root=tmp_path),
        dag_path=str(write_python_augmented_dagster_test_dag(root=tmp_path)),
    )

    invocation: SqlBuildCliInvocation = resource.cli(
        args=test_case.command_args,
        context=context,
    ).wait()

    assert invocation.selection == test_case.expected_selectors
    test_case.assert_selector_transport(
        command=invocation.command,
        selectors=test_case.expected_selectors,
    )


@pytest.mark.parametrize(
    "test_case",
    [
        DagsterCliSelectionTestCase(
            description="selected multi-asset check scopes every checked model",
            selected_asset_keys=(),
            command_args=("build",),
            expected_selectors=("orders", "customers"),
            assert_selector_transport=assert_select_file_selector_behavior,
            selected_check_keys=((("analytics", "orders"), "audit__not_null__order_id"),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_selected_multi_asset_check_when_invoking_build_then_scopes_every_checked_asset(
    test_case: DagsterCliSelectionTestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = tmp_path / "project"
    project_dir.mkdir()
    dag: dict[str, Any] = dict(build_dagster_test_dag())
    checks: list[dict[str, Any]] = [dict(check) for check in dag["checks"]]
    checks[0]["checked_asset_ids"] = ["model:orders", "model:customers"]
    dag["checks"] = checks
    dag_path: Path = tmp_path / "sqlbuild_dag.json"
    dag_path.write_text(json.dumps(dag), encoding="utf-8")
    context: Any = type(
        "SelectedCheckContext",
        (),
        {
            "selected_asset_keys": set(),
            "selected_asset_check_keys": {
                dg.AssetCheckKey(asset_key=dg.AssetKey(list(asset_key)), name=check_name)
                for asset_key, check_name in test_case.selected_check_keys
            },
        },
    )()
    resource: SqlBuildCliResource = SqlBuildCliResource(
        project_dir=str(project_dir),
        sqb_command=write_fake_sqb_command(root=tmp_path),
        dag_path=str(dag_path),
    )

    invocation: SqlBuildCliInvocation = resource.cli(
        args=test_case.command_args,
        context=context,
    ).wait()

    assert set(invocation.selection) == set(test_case.expected_selectors)
    test_case.assert_selector_transport(
        command=invocation.command,
        selectors=test_case.expected_selectors,
    )
