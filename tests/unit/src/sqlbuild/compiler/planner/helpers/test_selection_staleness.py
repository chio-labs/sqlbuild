from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.fingerprints.constants import NODE_TYPE_SEED
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner.helpers.selection_staleness import (
    build_stale_out_of_selection_warnings,
)
from sqlbuild.compiler.planner.models import (
    ChangeDetectionResult,
    PlannerChangeResults,
    PlannerScope,
    PlanWarning,
    StandardModelVersionIdentities,
    WarehouseFingerprints,
    WarehouseSnapshot,
)
from sqlbuild.compiler.planner.types import ChangeKind
from sqlbuild.compiler.source_freshness.models import (
    SourceFreshnessIdentity,
    StandardSourceFreshnessPlanningResult,
)
from tests.unit.src.sqlbuild.compiler.planner.helpers._test_types import (
    SelectionStalenessGraphWarningTestCase,
    SelectionStalenessWarningTestCase,
)

MODEL_KEY: CompiledObjectKey = CompiledObjectKey(
    resource_type=CompiledResourceType.MODEL,
    name="c",
)
SEED_KEY: CompiledObjectKey = CompiledObjectKey(
    resource_type=CompiledResourceType.SEED,
    name="orders_seed",
)
SOURCE_KEY: CompiledObjectKey = CompiledObjectKey(
    resource_type=CompiledResourceType.SOURCE,
    name="raw_orders",
)
SOURCE_IDENTITY: SourceFreshnessIdentity = SourceFreshnessIdentity(
    source_name="raw_orders",
    target_database=None,
    target_schema="raw",
    target_name="orders",
)
MODEL_A_KEY: CompiledObjectKey = CompiledObjectKey(
    resource_type=CompiledResourceType.MODEL,
    name="a",
)
MODEL_B_KEY: CompiledObjectKey = CompiledObjectKey(
    resource_type=CompiledResourceType.MODEL,
    name="b",
)
MODEL_D_KEY: CompiledObjectKey = CompiledObjectKey(
    resource_type=CompiledResourceType.MODEL,
    name="d",
)
SEED_ROOT_KEY: CompiledObjectKey = CompiledObjectKey(
    resource_type=CompiledResourceType.SEED,
    name="root_seed",
)
SOURCE_ROOT_KEY: CompiledObjectKey = CompiledObjectKey(
    resource_type=CompiledResourceType.SOURCE,
    name="root_source",
)

TEST_CASES: list[SelectionStalenessWarningTestCase] = [
    SelectionStalenessWarningTestCase(
        description="changed seed outside selection warns",
        upstream_key=SEED_KEY,
        execution_selected_keys=frozenset(),
        expected_warning_fragments=("selected model 'c' is stale", "orders_seed changed"),
    ),
    SelectionStalenessWarningTestCase(
        description="changed seed in selected closure does not warn",
        upstream_key=SEED_KEY,
        execution_selected_keys=frozenset({MODEL_KEY, SEED_KEY}),
        expected_warning_fragments=(),
    ),
    SelectionStalenessWarningTestCase(
        description="changed source outside selection warns",
        upstream_key=SOURCE_KEY,
        execution_selected_keys=frozenset(),
        expected_warning_fragments=("selected model 'c' is stale", "raw_orders changed"),
    ),
    SelectionStalenessWarningTestCase(
        description="changed source in selected closure does not warn",
        upstream_key=SOURCE_KEY,
        execution_selected_keys=frozenset({MODEL_KEY, SOURCE_KEY}),
        expected_warning_fragments=(),
    ),
]

GRAPH_TEST_CASES: list[SelectionStalenessGraphWarningTestCase] = [
    SelectionStalenessGraphWarningTestCase(
        description="multi-hop seed root warns for stale intermediate and seed",
        upstream_deps={
            MODEL_KEY: (MODEL_B_KEY,),
            MODEL_B_KEY: (SEED_ROOT_KEY,),
        },
        selected_keys=frozenset({MODEL_KEY}),
        execution_selected_keys=frozenset(),
        changed_model_names=frozenset(),
        changed_seed_names=frozenset({SEED_ROOT_KEY.name}),
        changed_source_names=frozenset(),
        expected_warning_fragments=(
            "selected model 'c' is stale",
            "b changed but will not be rebuilt or is stale",
            "root_seed changed but will not be rebuilt",
        ),
    ),
    SelectionStalenessGraphWarningTestCase(
        description="multi-hop source root warns for stale intermediate and source",
        upstream_deps={
            MODEL_KEY: (MODEL_B_KEY,),
            MODEL_B_KEY: (SOURCE_ROOT_KEY,),
        },
        selected_keys=frozenset({MODEL_KEY}),
        execution_selected_keys=frozenset(),
        changed_model_names=frozenset(),
        changed_seed_names=frozenset(),
        changed_source_names=frozenset({SOURCE_ROOT_KEY.name}),
        expected_warning_fragments=(
            "selected model 'c' is stale",
            "b changed but will not be rebuilt or is stale",
            "root_source changed but will not be rebuilt",
        ),
    ),
    SelectionStalenessGraphWarningTestCase(
        description="branching graph reports multiple unbuilt changed roots",
        upstream_deps={
            MODEL_KEY: (MODEL_B_KEY, MODEL_D_KEY),
            MODEL_B_KEY: (MODEL_A_KEY,),
        },
        selected_keys=frozenset({MODEL_KEY}),
        execution_selected_keys=frozenset(),
        changed_model_names=frozenset({MODEL_A_KEY.name, MODEL_D_KEY.name}),
        changed_seed_names=frozenset(),
        changed_source_names=frozenset(),
        expected_warning_fragments=(
            "selected model 'c' is stale",
            "a changed but will not be rebuilt",
            "b changed but will not be rebuilt or is stale",
            "d changed but will not be rebuilt",
        ),
    ),
    SelectionStalenessGraphWarningTestCase(
        description="mixed selected and unselected changed parents warns only for unselected",
        upstream_deps={
            MODEL_KEY: (MODEL_A_KEY, MODEL_B_KEY),
        },
        selected_keys=frozenset({MODEL_A_KEY, MODEL_KEY}),
        execution_selected_keys=frozenset({MODEL_A_KEY, MODEL_KEY}),
        changed_model_names=frozenset({MODEL_A_KEY.name, MODEL_B_KEY.name}),
        changed_seed_names=frozenset(),
        changed_source_names=frozenset(),
        expected_warning_fragments=(
            "selected model 'c' is stale",
            "b changed but will not be rebuilt",
        ),
        unexpected_warning_fragments=("a changed but will not be rebuilt",),
    ),
    SelectionStalenessGraphWarningTestCase(
        description="diamond graph reports both stale intermediates",
        upstream_deps={
            MODEL_KEY: (MODEL_B_KEY, MODEL_D_KEY),
            MODEL_B_KEY: (MODEL_A_KEY,),
            MODEL_D_KEY: (MODEL_A_KEY,),
        },
        selected_keys=frozenset({MODEL_KEY}),
        execution_selected_keys=frozenset(),
        changed_model_names=frozenset({MODEL_A_KEY.name}),
        changed_seed_names=frozenset(),
        changed_source_names=frozenset(),
        expected_warning_fragments=(
            "selected model 'c' is stale",
            "a changed but will not be rebuilt",
            "b changed but will not be rebuilt or is stale",
            "d changed but will not be rebuilt or is stale",
        ),
    ),
    SelectionStalenessGraphWarningTestCase(
        description="warning trigger list is capped",
        upstream_deps={
            MODEL_KEY: tuple(
                CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=f"a{i}")
                for i in range(1, 7)
            ),
        },
        selected_keys=frozenset({MODEL_KEY}),
        execution_selected_keys=frozenset(),
        changed_model_names=frozenset({f"a{i}" for i in range(1, 7)}),
        changed_seed_names=frozenset(),
        changed_source_names=frozenset(),
        expected_warning_fragments=(
            "selected model 'c' is stale",
            "a1 changed but will not be rebuilt",
            "a5 changed but will not be rebuilt",
            "+1 more",
        ),
    ),
    SelectionStalenessGraphWarningTestCase(
        description="cyclic stale graph terminates and reports changed root",
        upstream_deps={
            MODEL_KEY: (MODEL_B_KEY,),
            MODEL_B_KEY: (MODEL_KEY, MODEL_A_KEY),
        },
        selected_keys=frozenset({MODEL_KEY}),
        execution_selected_keys=frozenset(),
        changed_model_names=frozenset({MODEL_A_KEY.name}),
        changed_seed_names=frozenset(),
        changed_source_names=frozenset(),
        expected_warning_fragments=(
            "selected model 'c' is stale",
            "a changed but will not be rebuilt",
        ),
    ),
    SelectionStalenessGraphWarningTestCase(
        description="self cycle does not report selected model as its own trigger",
        upstream_deps={
            MODEL_KEY: (MODEL_KEY, MODEL_A_KEY),
        },
        selected_keys=frozenset({MODEL_KEY}),
        execution_selected_keys=frozenset(),
        changed_model_names=frozenset({MODEL_A_KEY.name}),
        changed_seed_names=frozenset(),
        changed_source_names=frozenset(),
        expected_warning_fragments=(
            "selected model 'c' is stale",
            "a changed but will not be rebuilt",
        ),
        unexpected_warning_fragments=("c changed but will not be rebuilt",),
    ),
]


@pytest.mark.parametrize("test_case", TEST_CASES, ids=[case.description for case in TEST_CASES])
def test_given_seed_or_source_change_when_classifying_then_warns_only_if_unselected(
    test_case: SelectionStalenessWarningTestCase,
) -> None:
    original_scope: PlannerScope = PlannerScope(
        upstream_deps={MODEL_KEY: (test_case.upstream_key,)},
        downstream_deps={test_case.upstream_key: (MODEL_KEY,)},
        all_keys={},
        models_by_name={},
        selected_keys=frozenset({MODEL_KEY}),
        execution_order=(test_case.upstream_key, MODEL_KEY),
    )
    execution_scope: PlannerScope = PlannerScope(
        upstream_deps=original_scope.upstream_deps,
        downstream_deps=original_scope.downstream_deps,
        all_keys={},
        models_by_name={},
        selected_keys=test_case.execution_selected_keys,
        execution_order=original_scope.execution_order,
    )

    warnings: tuple[PlanWarning, ...] = build_stale_out_of_selection_warnings(
        original_scope=original_scope,
        execution_scope=execution_scope,
        changes=PlannerChangeResults(models={}, functions={}),
        snapshot=WarehouseSnapshot(
            fingerprints=WarehouseFingerprints(
                seeds={
                    "orders_seed": Fingerprint(
                        node_type=NODE_TYPE_SEED,
                        node_name="orders_seed",
                        target_database=None,
                        target_schema="staging",
                        target_name="orders_seed",
                        run_id="previous_run",
                        definition_hash="old_seed_hash",
                        schema_fingerprint="",
                        definition="{}",
                        ts=datetime.now(UTC),
                        version_hash="old_seed_hash",
                    )
                }
            )
        ),
        version_identities=StandardModelVersionIdentities(
            function_local_hashes={},
            seed_version_hashes={"orders_seed": "new_seed_hash"},
            seed_metadata_jsons={},
            model_metadata_jsons={},
            model_local_hashes={},
            model_version_hashes={},
        ),
        source_freshness=StandardSourceFreshnessPlanningResult(
            changed_identities=frozenset({SOURCE_IDENTITY})
        ),
    )
    warning_text: str = "\n".join(warning.message for warning in warnings)

    assert ("is stale" in warning_text) == bool(test_case.expected_warning_fragments)
    expected_fragment: str
    for expected_fragment in test_case.expected_warning_fragments:
        assert expected_fragment in warning_text


@pytest.mark.parametrize(
    "test_case",
    GRAPH_TEST_CASES,
    ids=[case.description for case in GRAPH_TEST_CASES],
)
def test_given_stale_upstream_graph_when_classifying_then_reports_expected_triggers(
    test_case: SelectionStalenessGraphWarningTestCase,
) -> None:
    all_keys: set[CompiledObjectKey] = set(test_case.selected_keys)
    for child_key, parent_keys in test_case.upstream_deps.items():
        all_keys.add(child_key)
        all_keys.update(parent_keys)
    source_identities: frozenset[SourceFreshnessIdentity] = frozenset(
        SourceFreshnessIdentity(
            source_name=source_name,
            target_database=None,
            target_schema="raw",
            target_name=source_name,
        )
        for source_name in test_case.changed_source_names
    )
    seed_fingerprints: dict[str, Fingerprint] = {
        seed_name: Fingerprint(
            node_type=NODE_TYPE_SEED,
            node_name=seed_name,
            target_database=None,
            target_schema="staging",
            target_name=seed_name,
            run_id="previous_run",
            definition_hash="old_seed_hash",
            schema_fingerprint="",
            definition="{}",
            ts=datetime.now(UTC),
            version_hash="old_seed_hash",
        )
        for seed_name in test_case.changed_seed_names
    }
    original_scope: PlannerScope = PlannerScope(
        upstream_deps=test_case.upstream_deps,
        downstream_deps={},
        all_keys={key.name: key for key in all_keys},
        models_by_name={},
        selected_keys=test_case.selected_keys,
        execution_order=tuple(all_keys),
    )
    execution_scope: PlannerScope = PlannerScope(
        upstream_deps=original_scope.upstream_deps,
        downstream_deps=original_scope.downstream_deps,
        all_keys=original_scope.all_keys,
        models_by_name={},
        selected_keys=test_case.execution_selected_keys,
        execution_order=original_scope.execution_order,
    )

    warnings: tuple[PlanWarning, ...] = build_stale_out_of_selection_warnings(
        original_scope=original_scope,
        execution_scope=execution_scope,
        changes=PlannerChangeResults(
            models={
                model_name: ChangeDetectionResult(
                    model_name=model_name,
                    change_kind=ChangeKind.QUERY_CHANGED,
                )
                for model_name in test_case.changed_model_names
            },
            functions={},
        ),
        snapshot=WarehouseSnapshot(fingerprints=WarehouseFingerprints(seeds=seed_fingerprints)),
        version_identities=StandardModelVersionIdentities(
            function_local_hashes={},
            seed_version_hashes={
                seed_name: "new_seed_hash" for seed_name in test_case.changed_seed_names
            },
            seed_metadata_jsons={},
            model_metadata_jsons={},
            model_local_hashes={},
            model_version_hashes={},
        ),
        source_freshness=StandardSourceFreshnessPlanningResult(
            changed_identities=source_identities
        ),
    )
    warning_text: str = "\n".join(warning.message for warning in warnings)

    expected_fragment: str
    for expected_fragment in test_case.expected_warning_fragments:
        assert expected_fragment in warning_text
    unexpected_fragment: str
    for unexpected_fragment in test_case.unexpected_warning_fragments:
        assert unexpected_fragment not in warning_text
