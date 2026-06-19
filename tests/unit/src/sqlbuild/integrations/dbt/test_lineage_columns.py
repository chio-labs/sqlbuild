from __future__ import annotations

import json
from collections.abc import Mapping
from typing import cast

import pytest

from sqlbuild.adapter.shared.models import ColumnInfo
from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.integrations.dbt.exceptions import DbtInteropArgumentError
from sqlbuild.integrations.dbt.helpers.graph import build_dbt_combined_graph
from sqlbuild.integrations.dbt.helpers.lineage_columns import (
    inspect_dbt_source_schemas,
    select_dbt_column_lineage_target,
)
from sqlbuild.integrations.dbt.helpers.lineage_output import (
    format_dbt_column_lineage_json,
    format_dbt_column_lineage_list,
    format_dbt_column_lineage_tree,
)
from sqlbuild.integrations.dbt.helpers.manifest import build_dbt_manifest_index
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex
from sqlbuild.integrations.dbt.models import (
    DbtColumnLineageTrace,
    DbtCombinedGraph,
    DbtSourceSchemaInspectionResult,
)
from sqlbuild.integrations.dbt.types import DbtLineageDirection, DbtLineageOutputFormat
from sqlbuild.spec.models.source import SourceColumnEntry
from tests.unit.src.sqlbuild.integrations.dbt._test_types import (
    DbtColumnLineageErrorTestCase,
    DbtColumnLineageOutputTestCase,
    DbtColumnLineageSelectionTestCase,
)
from tests.unit.src.sqlbuild.integrations.dbt.helpers import (
    FakeLineageSourceSchemaAdapter,
    build_column_lineage_ambiguous_table_manifest_data,
    build_column_lineage_join_manifest_data,
    build_column_lineage_manifest_data,
    build_column_lineage_quoted_schema_manifest_data,
    build_column_lineage_star_manifest_data,
    build_compiled_project_with_models,
    build_manifest_data,
    build_manifest_model_node,
    column_lineage_edge_ids,
    column_lineage_target_id,
)

COLUMN_LINEAGE_TEST_CASES: tuple[DbtColumnLineageSelectionTestCase, ...] = (
    DbtColumnLineageSelectionTestCase(
        description="traces SQLBuild column upstream through compiled dbt SQL",
        target="downstream_orders:downstream_amount",
        direction=DbtLineageDirection.UPSTREAM,
        expected_edges=(
            ("model.analytics.fact_orders:amount", "downstream_orders:downstream_amount"),
            ("model.analytics.stg_orders:amount", "model.analytics.fact_orders:amount"),
            ("source.analytics.raw.orders:amount", "model.analytics.stg_orders:amount"),
        ),
        expected_target=("model", "downstream_orders", "downstream_amount"),
    ),
    DbtColumnLineageSelectionTestCase(
        description="traces dbt unique id column upstream",
        target="model.analytics.fact_orders:amount",
        direction=DbtLineageDirection.UPSTREAM,
        expected_edges=(
            ("model.analytics.stg_orders:amount", "model.analytics.fact_orders:amount"),
            ("source.analytics.raw.orders:amount", "model.analytics.stg_orders:amount"),
        ),
        expected_target=("model", "model.analytics.fact_orders", "amount"),
    ),
    DbtColumnLineageSelectionTestCase(
        description="traces dbt short name column upstream",
        target="fact_orders:amount",
        direction=DbtLineageDirection.UPSTREAM,
        expected_edges=(
            ("model.analytics.stg_orders:amount", "model.analytics.fact_orders:amount"),
            ("source.analytics.raw.orders:amount", "model.analytics.stg_orders:amount"),
        ),
        expected_target=("model", "model.analytics.fact_orders", "amount"),
    ),
    DbtColumnLineageSelectionTestCase(
        description="traces dbt source column downstream into SQLBuild model",
        target="source.analytics.raw.orders:amount",
        direction=DbtLineageDirection.DOWNSTREAM,
        expected_edges=(
            ("source.analytics.raw.orders:amount", "model.analytics.stg_orders:amount"),
            ("model.analytics.stg_orders:amount", "model.analytics.fact_orders:amount"),
            ("model.analytics.fact_orders:amount", "downstream_orders:downstream_amount"),
        ),
        expected_target=("source", "source.analytics.raw.orders", "amount"),
    ),
    DbtColumnLineageSelectionTestCase(
        description="limits downstream traversal with depth one",
        target="source.analytics.raw.orders:amount",
        direction=DbtLineageDirection.DOWNSTREAM,
        depth=1,
        expected_edges=(
            ("source.analytics.raw.orders:amount", "model.analytics.stg_orders:amount"),
        ),
        expected_target=("source", "source.analytics.raw.orders", "amount"),
        expected_truncated=True,
    ),
    DbtColumnLineageSelectionTestCase(
        description="returns no edges with depth zero",
        target="downstream_orders:downstream_amount",
        direction=DbtLineageDirection.UPSTREAM,
        depth=0,
        expected_edges=(),
        expected_target=("model", "downstream_orders", "downstream_amount"),
        expected_truncated=True,
    ),
)

COLUMN_LINEAGE_ERROR_TEST_CASES: tuple[DbtColumnLineageErrorTestCase, ...] = (
    DbtColumnLineageErrorTestCase(
        description="rejects both direction",
        target="downstream_orders:downstream_amount",
        direction=DbtLineageDirection.BOTH,
        expected_error_fragment="supports --direction upstream or downstream",
        expected_code="C336",
    ),
    DbtColumnLineageErrorTestCase(
        description="rejects ambiguous dbt short name",
        target="orders:amount",
        direction=DbtLineageDirection.UPSTREAM,
        expected_error_fragment="ambiguous dbt lineage target 'orders'",
        expected_code="C330",
    ),
    DbtColumnLineageErrorTestCase(
        description="rejects unknown resource",
        target="missing_orders:amount",
        direction=DbtLineageDirection.UPSTREAM,
        expected_error_fragment="unknown dbt lineage target 'missing_orders'",
        expected_code="C331",
    ),
)

COLUMN_LINEAGE_OUTPUT_TEST_CASES: tuple[DbtColumnLineageOutputTestCase, ...] = (
    DbtColumnLineageOutputTestCase(
        description="formats list output",
        output_format=DbtLineageOutputFormat.LIST,
        expected_fragments=(
            "Column dependencies",
            "model.analytics.fact_orders:amount",
            "downstream_orders:downstream_amount",
            "direct",
        ),
    ),
    DbtColumnLineageOutputTestCase(
        description="formats tree output",
        output_format=DbtLineageOutputFormat.TREE,
        expected_fragments=(
            "Column trace",
            "downstream_orders:downstream_amount",
            "model.analytics.fact_orders:amount",
        ),
    ),
)

UNQUALIFIED_REF_COLUMN_LINEAGE_TEST_CASES: tuple[DbtColumnLineageSelectionTestCase, ...] = (
    DbtColumnLineageSelectionTestCase(
        description="traces unqualified SQLBuild dbt ref",
        target="downstream_orders:downstream_amount",
        direction=DbtLineageDirection.UPSTREAM,
        expected_edges=(
            ("model.analytics.fact_orders:amount", "downstream_orders:downstream_amount"),
            ("model.analytics.stg_orders:amount", "model.analytics.fact_orders:amount"),
            ("source.analytics.raw.orders:amount", "model.analytics.stg_orders:amount"),
        ),
    ),
    DbtColumnLineageSelectionTestCase(
        description="returns no edges for unknown column",
        target="downstream_orders:missing_amount",
        direction=DbtLineageDirection.UPSTREAM,
        expected_edges=(),
    ),
)

STAR_COLUMN_LINEAGE_TEST_CASES: tuple[DbtColumnLineageSelectionTestCase, ...] = (
    DbtColumnLineageSelectionTestCase(
        description="expands star using inspected source schema and propagated model schema",
        target="model.analytics.fact_orders:amount",
        direction=DbtLineageDirection.UPSTREAM,
        expected_edges=(
            ("model.analytics.stg_orders:amount", "model.analytics.fact_orders:amount"),
            ("source.analytics.raw.orders:amount", "model.analytics.stg_orders:amount"),
        ),
    ),
    DbtColumnLineageSelectionTestCase(
        description="does not trust dbt manifest columns for star expansion",
        target="model.analytics.fact_orders:amount",
        direction=DbtLineageDirection.UPSTREAM,
        expected_edges=(),
    ),
)

SOURCE_SCHEMA_INSPECTION_TEST_CASES: tuple[DbtColumnLineageSelectionTestCase, ...] = (
    DbtColumnLineageSelectionTestCase(
        description="inspects source schema with fallback relation name",
        target="source.analytics.raw.orders:amount",
        direction=DbtLineageDirection.UPSTREAM,
        expected_edges=(),
        expected_warnings=(),
    ),
    DbtColumnLineageSelectionTestCase(
        description="warns when source schema cannot be inspected",
        target="source.analytics.raw.orders:amount",
        direction=DbtLineageDirection.UPSTREAM,
        expected_edges=(),
        expected_warnings=(
            "Could not inspect source source.analytics.raw.orders; "
            "SELECT * lineage from this source may be incomplete: "
            'missing relation "db"."raw"."orders"; missing relation raw.orders; '
            'missing relation "raw"."orders"; missing relation orders',
        ),
    ),
)


@pytest.mark.parametrize(
    "test_case",
    COLUMN_LINEAGE_TEST_CASES,
    ids=[case.description for case in COLUMN_LINEAGE_TEST_CASES],
)
def test_given_compiled_dbt_sql_when_selecting_column_lineage_then_traces_mixed_columns(
    test_case: DbtColumnLineageSelectionTestCase,
) -> None:
    manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=build_column_lineage_manifest_data()
    )
    project: CompiledProject = build_compiled_project_with_models(
        {
            "downstream_orders": (
                'select amount as downstream_amount from __dbt_ref("analytics", "fact_orders")'
            )
        }
    )
    graph: DbtCombinedGraph = build_dbt_combined_graph(manifest=manifest, project=project)

    trace: DbtColumnLineageTrace | None = select_dbt_column_lineage_target(
        project=project,
        manifest=manifest,
        graph=graph,
        target=test_case.target,
        direction=test_case.direction,
        depth=test_case.depth,
        source_schemas=DbtSourceSchemaInspectionResult(
            columns_by_unique_id={
                "source.analytics.raw.orders": (
                    SourceColumnEntry(name="order_id", type="INTEGER"),
                    SourceColumnEntry(name="amount", type="INTEGER"),
                )
            },
            warnings=test_case.expected_warnings,
        ),
    )

    assert trace is not None
    assert tuple(column_lineage_edge_ids(edge) for edge in trace.trace) == test_case.expected_edges
    assert trace.warnings == test_case.expected_warnings
    assert column_lineage_target_id(trace) == test_case.expected_target
    assert trace.truncated == test_case.expected_truncated


@pytest.mark.parametrize(
    "test_case",
    COLUMN_LINEAGE_ERROR_TEST_CASES,
    ids=[case.description for case in COLUMN_LINEAGE_ERROR_TEST_CASES],
)
def test_given_invalid_column_lineage_target_when_selecting_then_raises_clear_error(
    test_case: DbtColumnLineageErrorTestCase,
) -> None:
    manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=build_manifest_data(
            nodes=(
                build_manifest_model_node(
                    unique_id="model.analytics.orders",
                    package_name="analytics",
                    name="orders",
                    relation_name="analytics.orders",
                ),
                build_manifest_model_node(
                    unique_id="model.stripe.orders",
                    package_name="stripe",
                    name="orders",
                    relation_name="stripe.orders",
                ),
            )
        )
    )
    project: CompiledProject = build_compiled_project_with_models(
        {"downstream_orders": "select 1 as downstream_amount"}
    )
    graph: DbtCombinedGraph = build_dbt_combined_graph(manifest=manifest, project=project)

    with pytest.raises(DbtInteropArgumentError) as exc_info:
        select_dbt_column_lineage_target(
            project=project,
            manifest=manifest,
            graph=graph,
            target=test_case.target,
            direction=test_case.direction,
            depth=None,
            source_schemas=DbtSourceSchemaInspectionResult(columns_by_unique_id={}),
        )

    assert test_case.expected_error_fragment in str(exc_info.value)
    assert exc_info.value.code == test_case.expected_code


@pytest.mark.parametrize(
    "test_case",
    [
        DbtColumnLineageSelectionTestCase(
            description="ignores malformed column target",
            target="downstream_orders:",
            direction=DbtLineageDirection.UPSTREAM,
            expected_edges=(),
            expected_is_column_target=False,
        )
    ],
    ids=["ignores malformed column target"],
)
def test_given_malformed_column_lineage_target_when_selecting_then_returns_none(
    test_case: DbtColumnLineageSelectionTestCase,
) -> None:
    manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=build_column_lineage_manifest_data()
    )
    project: CompiledProject = build_compiled_project_with_models(
        {"downstream_orders": "select 1 as downstream_amount"}
    )
    graph: DbtCombinedGraph = build_dbt_combined_graph(manifest=manifest, project=project)

    trace: DbtColumnLineageTrace | None = select_dbt_column_lineage_target(
        project=project,
        manifest=manifest,
        graph=graph,
        target=test_case.target,
        direction=test_case.direction,
        depth=None,
        source_schemas=DbtSourceSchemaInspectionResult(columns_by_unique_id={}),
    )

    assert (trace is not None) == test_case.expected_is_column_target


@pytest.mark.parametrize(
    "test_case",
    [
        DbtColumnLineageSelectionTestCase(
            description="serializes source schema warning",
            target="downstream_orders:downstream_amount",
            direction=DbtLineageDirection.UPSTREAM,
            expected_edges=(
                ("model.analytics.fact_orders:amount", "downstream_orders:downstream_amount"),
                ("model.analytics.stg_orders:amount", "model.analytics.fact_orders:amount"),
                ("source.analytics.raw.orders:amount", "model.analytics.stg_orders:amount"),
            ),
            expected_warnings=("Could not inspect source source.analytics.raw.orders",),
        )
    ],
    ids=["serializes source schema warning"],
)
def test_given_source_schema_warning_when_formatting_json_then_includes_warning(
    test_case: DbtColumnLineageSelectionTestCase,
) -> None:
    manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=build_column_lineage_manifest_data()
    )
    project: CompiledProject = build_compiled_project_with_models(
        {
            "downstream_orders": (
                'select amount as downstream_amount from __dbt_ref("analytics", "fact_orders")'
            )
        }
    )
    graph: DbtCombinedGraph = build_dbt_combined_graph(manifest=manifest, project=project)

    trace: DbtColumnLineageTrace | None = select_dbt_column_lineage_target(
        project=project,
        manifest=manifest,
        graph=graph,
        target=test_case.target,
        direction=test_case.direction,
        depth=None,
        source_schemas=DbtSourceSchemaInspectionResult(
            columns_by_unique_id={},
            warnings=test_case.expected_warnings,
        ),
    )

    assert trace is not None
    payload: object = json.loads(format_dbt_column_lineage_json(trace))
    assert isinstance(payload, dict)
    metadata: object = payload["metadata"]
    assert isinstance(metadata, dict)
    assert cast(Mapping[str, object], metadata)["warnings"] == list(test_case.expected_warnings)
    assert tuple(column_lineage_edge_ids(edge) for edge in trace.trace) == test_case.expected_edges


@pytest.mark.parametrize(
    "test_case",
    UNQUALIFIED_REF_COLUMN_LINEAGE_TEST_CASES,
    ids=[case.description for case in UNQUALIFIED_REF_COLUMN_LINEAGE_TEST_CASES],
)
def test_given_unqualified_dbt_ref_or_unknown_column_when_selecting_then_returns_expected_trace(
    test_case: DbtColumnLineageSelectionTestCase,
) -> None:
    manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=build_column_lineage_manifest_data()
    )
    project: CompiledProject = build_compiled_project_with_models(
        {"downstream_orders": 'select amount as downstream_amount from __dbt_ref("fact_orders")'}
    )
    graph: DbtCombinedGraph = build_dbt_combined_graph(manifest=manifest, project=project)

    trace: DbtColumnLineageTrace | None = select_dbt_column_lineage_target(
        project=project,
        manifest=manifest,
        graph=graph,
        target=test_case.target,
        direction=test_case.direction,
        depth=None,
        source_schemas=DbtSourceSchemaInspectionResult(
            columns_by_unique_id={
                "source.analytics.raw.orders": (SourceColumnEntry(name="amount", type="INTEGER"),)
            }
        ),
    )

    assert trace is not None
    assert tuple(column_lineage_edge_ids(edge) for edge in trace.trace) == test_case.expected_edges


@pytest.mark.parametrize(
    "test_case",
    COLUMN_LINEAGE_OUTPUT_TEST_CASES,
    ids=[case.description for case in COLUMN_LINEAGE_OUTPUT_TEST_CASES],
)
def test_given_column_lineage_trace_when_formatting_human_output_then_includes_expected_fragments(
    test_case: DbtColumnLineageOutputTestCase,
) -> None:
    manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=build_column_lineage_manifest_data()
    )
    project: CompiledProject = build_compiled_project_with_models(
        {
            "downstream_orders": (
                'select amount as downstream_amount from __dbt_ref("analytics", "fact_orders")'
            )
        }
    )
    graph: DbtCombinedGraph = build_dbt_combined_graph(manifest=manifest, project=project)
    trace: DbtColumnLineageTrace | None = select_dbt_column_lineage_target(
        project=project,
        manifest=manifest,
        graph=graph,
        target="downstream_orders:downstream_amount",
        direction=DbtLineageDirection.UPSTREAM,
        depth=None,
        source_schemas=DbtSourceSchemaInspectionResult(columns_by_unique_id={}),
    )

    assert trace is not None
    outputs: dict[DbtLineageOutputFormat, str] = {
        DbtLineageOutputFormat.LIST: format_dbt_column_lineage_list(trace, use_color=False),
        DbtLineageOutputFormat.TREE: format_dbt_column_lineage_tree(trace, use_color=False),
    }
    output: str = outputs[test_case.output_format]
    expected_fragment: str
    for expected_fragment in test_case.expected_fragments:
        assert expected_fragment in output


@pytest.mark.parametrize(
    "test_case",
    [
        DbtColumnLineageOutputTestCase(
            description="formats no edge tree output",
            output_format=DbtLineageOutputFormat.TREE,
            expected_fragments=("Column trace", "No column dependencies found"),
        )
    ],
    ids=["formats no edge tree output"],
)
def test_given_no_edge_column_trace_when_formatting_tree_then_explains_no_dependencies(
    test_case: DbtColumnLineageOutputTestCase,
) -> None:
    manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=build_column_lineage_manifest_data()
    )
    project: CompiledProject = build_compiled_project_with_models(
        {"downstream_orders": "select 1 as downstream_amount"}
    )
    graph: DbtCombinedGraph = build_dbt_combined_graph(manifest=manifest, project=project)
    trace: DbtColumnLineageTrace | None = select_dbt_column_lineage_target(
        project=project,
        manifest=manifest,
        graph=graph,
        target="downstream_orders:downstream_amount",
        direction=DbtLineageDirection.UPSTREAM,
        depth=None,
        source_schemas=DbtSourceSchemaInspectionResult(columns_by_unique_id={}),
    )

    assert trace is not None
    output: str = format_dbt_column_lineage_tree(trace, use_color=False)
    expected_fragment: str
    for expected_fragment in test_case.expected_fragments:
        assert expected_fragment in output


@pytest.mark.parametrize(
    "test_case",
    STAR_COLUMN_LINEAGE_TEST_CASES,
    ids=[case.description for case in STAR_COLUMN_LINEAGE_TEST_CASES],
)
def test_given_star_dbt_sql_when_selecting_column_lineage_then_uses_only_inspected_schema(
    test_case: DbtColumnLineageSelectionTestCase,
) -> None:
    manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=build_column_lineage_star_manifest_data(include_source_schema=True)
    )
    project: CompiledProject = build_compiled_project_with_models({})
    graph: DbtCombinedGraph = build_dbt_combined_graph(manifest=manifest, project=project)
    source_schemas_by_description: dict[str, DbtSourceSchemaInspectionResult] = {
        "expands star using inspected source schema and propagated model schema": (
            DbtSourceSchemaInspectionResult(
                columns_by_unique_id={
                    "source.analytics.raw.orders": (
                        SourceColumnEntry(name="order_id", type="INTEGER"),
                        SourceColumnEntry(name="amount", type="INTEGER"),
                    )
                }
            )
        ),
        "does not trust dbt manifest columns for star expansion": DbtSourceSchemaInspectionResult(
            columns_by_unique_id={}
        ),
    }

    trace: DbtColumnLineageTrace | None = select_dbt_column_lineage_target(
        project=project,
        manifest=manifest,
        graph=graph,
        target=test_case.target,
        direction=test_case.direction,
        depth=None,
        source_schemas=source_schemas_by_description[test_case.description],
    )

    assert trace is not None
    assert tuple(column_lineage_edge_ids(edge) for edge in trace.trace) == test_case.expected_edges


@pytest.mark.parametrize(
    "test_case",
    [
        DbtColumnLineageSelectionTestCase(
            description="rewrites aliases joins unquoted relations and classifies expression",
            target="model.analytics.fact_orders:amount_cents",
            direction=DbtLineageDirection.UPSTREAM,
            expected_edges=(
                ("model.analytics.stg_orders:amount", "model.analytics.fact_orders:amount_cents"),
                ("source.analytics.raw.orders:amount", "model.analytics.stg_orders:amount"),
            ),
            expected_transforms=("expression", "direct"),
            expected_confidences=("high", "high"),
        )
    ],
    ids=["rewrites aliases joins unquoted relations and classifies expression"],
)
def test_given_alias_join_and_expression_when_selecting_column_lineage_then_traces_and_classifies(
    test_case: DbtColumnLineageSelectionTestCase,
) -> None:
    manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=build_column_lineage_join_manifest_data()
    )
    project: CompiledProject = build_compiled_project_with_models({})
    graph: DbtCombinedGraph = build_dbt_combined_graph(manifest=manifest, project=project)

    trace: DbtColumnLineageTrace | None = select_dbt_column_lineage_target(
        project=project,
        manifest=manifest,
        graph=graph,
        target=test_case.target,
        direction=test_case.direction,
        depth=None,
        source_schemas=DbtSourceSchemaInspectionResult(
            columns_by_unique_id={
                "source.analytics.raw.orders": (
                    SourceColumnEntry(name="order_id", type="INTEGER"),
                    SourceColumnEntry(name="amount", type="INTEGER"),
                ),
                "source.analytics.raw.customers": (
                    SourceColumnEntry(name="order_id", type="INTEGER"),
                ),
            }
        ),
    )

    assert trace is not None
    assert tuple(column_lineage_edge_ids(edge) for edge in trace.trace) == test_case.expected_edges
    assert tuple(str(edge.transform_kind) for edge in trace.trace) == test_case.expected_transforms
    assert tuple(str(edge.confidence) for edge in trace.trace) == test_case.expected_confidences
    payload: object = json.loads(format_dbt_column_lineage_json(trace))
    assert isinstance(payload, dict)
    trace_payload: object = payload["trace"]
    assert isinstance(trace_payload, list)
    assert [cast(Mapping[str, object], edge)["transform"] for edge in trace_payload] == list(
        test_case.expected_transforms
    )
    assert [cast(Mapping[str, object], edge)["confidence"] for edge in trace_payload] == list(
        test_case.expected_confidences
    )


@pytest.mark.parametrize(
    "test_case",
    [
        DbtColumnLineageSelectionTestCase(
            description="rewrites quoted schema-qualified compiled relations",
            target="model.analytics.fact_orders:amount",
            direction=DbtLineageDirection.UPSTREAM,
            expected_edges=(
                ("model.analytics.stg_orders:amount", "model.analytics.fact_orders:amount"),
                ("source.analytics.raw.orders:amount", "model.analytics.stg_orders:amount"),
            ),
        )
    ],
    ids=["rewrites quoted schema-qualified compiled relations"],
)
def test_given_quoted_schema_qualified_relations_when_selecting_column_lineage_then_traces_columns(
    test_case: DbtColumnLineageSelectionTestCase,
) -> None:
    manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=build_column_lineage_quoted_schema_manifest_data()
    )
    project: CompiledProject = build_compiled_project_with_models({})
    graph: DbtCombinedGraph = build_dbt_combined_graph(manifest=manifest, project=project)

    trace: DbtColumnLineageTrace | None = select_dbt_column_lineage_target(
        project=project,
        manifest=manifest,
        graph=graph,
        target=test_case.target,
        direction=test_case.direction,
        depth=None,
        source_schemas=DbtSourceSchemaInspectionResult(
            columns_by_unique_id={
                "source.analytics.raw.orders": (
                    SourceColumnEntry(name="order_id", type="INTEGER"),
                    SourceColumnEntry(name="amount", type="INTEGER"),
                )
            }
        ),
    )

    assert trace is not None
    assert tuple(column_lineage_edge_ids(edge) for edge in trace.trace) == test_case.expected_edges


@pytest.mark.parametrize(
    "test_case",
    [
        DbtColumnLineageSelectionTestCase(
            description="does not rewrite ambiguous table-only compiled relation",
            target="model.analytics.fact_orders:amount",
            direction=DbtLineageDirection.UPSTREAM,
            expected_edges=(),
        )
    ],
    ids=["does not rewrite ambiguous table-only compiled relation"],
)
def test_given_ambiguous_table_only_relation_when_selecting_column_lineage_then_avoids_guessing(
    test_case: DbtColumnLineageSelectionTestCase,
) -> None:
    manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=build_column_lineage_ambiguous_table_manifest_data()
    )
    project: CompiledProject = build_compiled_project_with_models({})
    graph: DbtCombinedGraph = build_dbt_combined_graph(manifest=manifest, project=project)

    trace: DbtColumnLineageTrace | None = select_dbt_column_lineage_target(
        project=project,
        manifest=manifest,
        graph=graph,
        target=test_case.target,
        direction=test_case.direction,
        depth=None,
        source_schemas=DbtSourceSchemaInspectionResult(
            columns_by_unique_id={
                "source.analytics.raw.orders": (SourceColumnEntry(name="amount", type="INTEGER"),),
                "source.analytics.archive.orders": (
                    SourceColumnEntry(name="amount", type="INTEGER"),
                ),
            }
        ),
    )

    assert trace is not None
    assert tuple(column_lineage_edge_ids(edge) for edge in trace.trace) == test_case.expected_edges


@pytest.mark.parametrize(
    "test_case",
    SOURCE_SCHEMA_INSPECTION_TEST_CASES,
    ids=[case.description for case in SOURCE_SCHEMA_INSPECTION_TEST_CASES],
)
def test_given_source_schema_inspection_when_describing_sources_then_returns_columns_or_warnings(
    test_case: DbtColumnLineageSelectionTestCase,
) -> None:
    manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=build_column_lineage_manifest_data()
    )
    adapter_by_description: dict[str, FakeLineageSourceSchemaAdapter] = {
        "inspects source schema with fallback relation name": FakeLineageSourceSchemaAdapter(
            {
                "raw.orders": (
                    ColumnInfo(name="order_id", type="INTEGER"),
                    ColumnInfo(name="amount", type="INTEGER"),
                )
            }
        ),
        "warns when source schema cannot be inspected": FakeLineageSourceSchemaAdapter({}),
    }
    expected_columns_by_description: dict[str, tuple[str, ...]] = {
        "inspects source schema with fallback relation name": ("order_id", "amount"),
        "warns when source schema cannot be inspected": (),
    }

    result: DbtSourceSchemaInspectionResult = inspect_dbt_source_schemas(
        adapter=adapter_by_description[test_case.description],
        connection_config={},
        manifest=manifest,
    )

    assert tuple(result.warnings) == test_case.expected_warnings
    assert (
        tuple(
            column.name
            for column in result.columns_by_unique_id.get("source.analytics.raw.orders", ())
        )
        == expected_columns_by_description[test_case.description]
    )
