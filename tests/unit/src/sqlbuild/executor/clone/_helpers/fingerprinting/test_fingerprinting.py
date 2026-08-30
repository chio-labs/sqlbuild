from __future__ import annotations

from typing import Any, cast

import pytest

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.fingerprints.constants import NODE_TYPE_MODEL, NODE_TYPE_SEED
from sqlbuild.compiler.fingerprints.models import Fingerprint, FingerprintSet
from sqlbuild.compiler.planner.models import ModelPlanEntry, SeedPlanEntry
from sqlbuild.compiler.planner.types import MaterializationType
from sqlbuild.executor.clone._helpers.fingerprinting import copy_clone_fingerprints
from sqlbuild.executor.clone.models import CloneExecutionResult, CloneItemResult
from sqlbuild.executor.clone.types import CloneAction, CloneStatus
from tests.unit.src.sqlbuild.executor.clone._helpers.fingerprinting._test_types import (
    CloneFingerprintPropagationTestCase,
    CloneFingerprintReadDedupTestCase,
)
from tests.unit.src.sqlbuild.executor.clone._helpers.fingerprinting.helpers import (
    CloneFingerprintAdapter,
    build_fingerprint,
    build_model_entry,
    build_seed_entry,
    patch_fingerprint_io,
)


@pytest.mark.parametrize(
    "test_case",
    [
        CloneFingerprintPropagationTestCase(
            description="copies table and seed fingerprints for successful physical clones",
            cloned_actions=(("orders", CloneAction.CLONED), ("countries", CloneAction.COPIED)),
            expected_written_identities=(
                (NODE_TYPE_SEED, "countries"),
                (NODE_TYPE_MODEL, "orders"),
            ),
        ),
        CloneFingerprintPropagationTestCase(
            description="skips recreated view fingerprints",
            cloned_actions=(("orders_view", CloneAction.RECREATED_VIEW),),
            expected_written_identities=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_clone_result_when_copying_fingerprints_then_writes_expected_rows(
    test_case: CloneFingerprintPropagationTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    written: list[tuple[str, str, str | None, str | None, str]] = []
    used_connections: list[object] = []

    def read_latest(**kwargs: Any) -> FingerprintSet:
        used_connections.append(kwargs["connection"])
        schema: str = str(kwargs["schema"])
        return FingerprintSet(
            schema=schema,
            fingerprints={},
            fingerprints_by_identity={
                (NODE_TYPE_MODEL, "orders"): build_fingerprint(NODE_TYPE_MODEL, "orders"),
                (NODE_TYPE_MODEL, "orders_view"): build_fingerprint(NODE_TYPE_MODEL, "orders_view"),
                (NODE_TYPE_SEED, "countries"): build_fingerprint(NODE_TYPE_SEED, "countries"),
            },
        )

    def write_fingerprint(**kwargs: Any) -> None:
        used_connections.append(kwargs["connection"])
        fingerprint: Fingerprint = kwargs["fingerprint"]
        written.append(
            (
                fingerprint.node_type,
                fingerprint.node_name,
                fingerprint.target_schema,
                fingerprint.target_name,
                fingerprint.run_id,
            )
        )

    patch_fingerprint_io(monkeypatch, read_latest=read_latest, write=write_fingerprint)
    origin_model_entries: tuple[ModelPlanEntry, ...] = (
        build_model_entry("orders", schema="prod", materialization=MaterializationType.TABLE),
        build_model_entry("orders_view", schema="prod", materialization=MaterializationType.VIEW),
    )
    destination_model_entries: tuple[ModelPlanEntry, ...] = (
        build_model_entry("orders", schema="dev", materialization=MaterializationType.TABLE),
        build_model_entry("orders_view", schema="dev", materialization=MaterializationType.VIEW),
    )
    origin_seed_entries: tuple[SeedPlanEntry, ...] = (build_seed_entry("countries", schema="prod"),)
    destination_seed_entries: tuple[SeedPlanEntry, ...] = (
        build_seed_entry("countries", schema="dev"),
    )
    result: CloneExecutionResult = CloneExecutionResult(
        item_results=tuple(
            CloneItemResult(name=name, action=action, status=CloneStatus.SUCCESS)
            for name, action in test_case.cloned_actions
        )
    )

    destination_connection: object = object()
    copy_clone_fingerprints(
        result=result,
        origin_model_entries=origin_model_entries,
        destination_model_entries=destination_model_entries,
        origin_seed_entries=origin_seed_entries,
        destination_seed_entries=destination_seed_entries,
        adapter=cast(BaseAdapter, CloneFingerprintAdapter()),
        destination_connection=destination_connection,
        run_id="clone-run",
        query_change_tracking=True,
    )

    assert tuple((node_type, node_name) for node_type, node_name, *_ in written) == (
        test_case.expected_written_identities
    )
    assert all(target_schema == "dev" for _, _, target_schema, _, _ in written)
    assert all(run_id == "clone-run" for *_, run_id in written)
    assert bool(used_connections) is bool(test_case.expected_written_identities)
    assert all(connection is destination_connection for connection in used_connections)


@pytest.mark.parametrize(
    "test_case",
    [
        CloneFingerprintReadDedupTestCase(
            description="reads origin fingerprints once for many entries sharing one schema",
            model_names=("orders", "payments", "customers"),
            origin_schema="prod",
            expected_read_schemas=("prod",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_many_entries_one_schema_when_copying_then_reads_origin_fingerprints_once(
    test_case: CloneFingerprintReadDedupTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    read_schemas: list[str | None] = []

    def read_latest(**kwargs: Any) -> FingerprintSet:
        read_schemas.append(kwargs.get("schema"))
        return FingerprintSet(
            schema=str(kwargs["schema"]),
            fingerprints={},
            fingerprints_by_identity={
                (NODE_TYPE_MODEL, name): build_fingerprint(NODE_TYPE_MODEL, name)
                for name in test_case.model_names
            },
        )

    patch_fingerprint_io(monkeypatch, read_latest=read_latest, write=lambda **_: None)
    origin_model_entries: tuple[ModelPlanEntry, ...] = tuple(
        build_model_entry(
            name, schema=test_case.origin_schema, materialization=MaterializationType.TABLE
        )
        for name in test_case.model_names
    )
    destination_model_entries: tuple[ModelPlanEntry, ...] = tuple(
        build_model_entry(name, schema="dev", materialization=MaterializationType.TABLE)
        for name in test_case.model_names
    )
    result: CloneExecutionResult = CloneExecutionResult(
        item_results=tuple(
            CloneItemResult(name=name, action=CloneAction.CLONED, status=CloneStatus.SUCCESS)
            for name in test_case.model_names
        )
    )

    copy_clone_fingerprints(
        result=result,
        origin_model_entries=origin_model_entries,
        destination_model_entries=destination_model_entries,
        origin_seed_entries=(),
        destination_seed_entries=(),
        adapter=cast(BaseAdapter, CloneFingerprintAdapter()),
        destination_connection=object(),
        run_id="clone-run",
        query_change_tracking=True,
    )

    assert tuple(read_schemas) == test_case.expected_read_schemas
