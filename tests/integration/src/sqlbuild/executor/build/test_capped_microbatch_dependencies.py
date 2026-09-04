"""Compile-time validation for capped microbatch producer dependencies."""

from pathlib import Path

import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.spec.contracts.types import MicrobatchLimitAction
from tests.integration.src.sqlbuild.executor.build._test_types import (
    CappedFilterConsumerTestCase,
    CappedIntermediateFilterTestCase,
    CappedIntermediateWatermarkTestCase,
    CappedWatermarkRejectionTestCase,
    PlainCappedConsumerTestCase,
    UncappedWatermarkChainTestCase,
)
from tests.integration.src.sqlbuild.executor.build.helpers import (
    capped_dependency_consumer_sql,
    capped_filter_consumer_sql,
    compile_capped_dependency_project,
    compile_capped_microbatch_intermediary_project,
    plain_capped_consumer_sql,
)


@pytest.mark.parametrize(
    "test_case",
    (
        CappedWatermarkRejectionTestCase(
            description="cap from start with all watermarks",
            limit_action=MicrobatchLimitAction.CAP_FROM_START,
            watermark_mode="all",
            watermark_input_name="capped_events",
            intermediary_names=(),
            expected_error_fragment=(
                "model 'downstream_events' uses capped producer 'capped_events' as a watermark "
                "input; capped producers cannot serve as watermark inputs"
            ),
        ),
        CappedWatermarkRejectionTestCase(
            description="cap from end with any watermarks",
            limit_action=MicrobatchLimitAction.CAP_FROM_END,
            watermark_mode="any",
            watermark_input_name="capped_events",
            intermediary_names=(),
            expected_error_fragment=(
                "model 'downstream_events' uses capped producer 'capped_events' as a watermark "
                "input; capped producers cannot serve as watermark inputs"
            ),
        ),
        CappedWatermarkRejectionTestCase(
            description="one intermediary view",
            limit_action=MicrobatchLimitAction.CAP_FROM_END,
            watermark_mode="all",
            watermark_input_name="events_view",
            intermediary_names=("events_view",),
            expected_error_fragment=(
                "model 'downstream_events' uses watermark input 'events_view' derived from "
                "capped producer 'capped_events'; capped producers cannot serve as watermark inputs"
            ),
        ),
        CappedWatermarkRejectionTestCase(
            description="multiple intermediary views",
            limit_action=MicrobatchLimitAction.CAP_FROM_START,
            watermark_mode="any",
            watermark_input_name="events_view_enriched",
            intermediary_names=("events_view", "events_view_enriched"),
            expected_error_fragment=(
                "model 'downstream_events' uses watermark input 'events_view_enriched' derived "
                "from capped producer 'capped_events'; capped producers cannot serve as watermark "
                "inputs"
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_capped_producer_when_used_as_watermark_then_compile_rejects_edge(
    tmp_path: Path,
    adapter: DuckDbAdapter,
    test_case: CappedWatermarkRejectionTestCase,
) -> None:
    with pytest.raises(CompileInputError, match=test_case.expected_error_fragment):
        compile_capped_dependency_project(
            project_dir=tmp_path,
            adapter=adapter,
            action=test_case.limit_action,
            consumer_sql=capped_dependency_consumer_sql(
                watermark_mode=test_case.watermark_mode,
                input_name=test_case.watermark_input_name,
            ),
            intermediary_names=test_case.intermediary_names,
        )


@pytest.mark.parametrize(
    "test_case",
    (
        CappedFilterConsumerTestCase(
            description="capped producer used only for filtering",
            limit_action=MicrobatchLimitAction.CAP_FROM_END,
            filter_input_name="events_view",
            intermediary_names=("events_view",),
            expected_model_names=("capped_events", "events_view", "downstream_events"),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_capped_producer_when_used_only_as_filter_then_microbatch_compile_succeeds(
    tmp_path: Path, adapter: DuckDbAdapter, test_case: CappedFilterConsumerTestCase
) -> None:
    result: CompilePipelineResult = compile_capped_dependency_project(
        project_dir=tmp_path,
        adapter=adapter,
        action=test_case.limit_action,
        consumer_sql=capped_filter_consumer_sql(input_name=test_case.filter_input_name),
        intermediary_names=test_case.intermediary_names,
    )

    assert (
        tuple(entry.name for entry in result.plan_output.model_entries)
        == test_case.expected_model_names
    )


@pytest.mark.parametrize(
    "test_case",
    (
        UncappedWatermarkChainTestCase(
            description="uncapped multi-level watermark chain",
            watermark_input_name="events_view_enriched",
            intermediary_names=("events_view", "events_view_enriched"),
            expected_model_names=(
                "capped_events",
                "events_view",
                "events_view_enriched",
                "downstream_events",
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_uncapped_chain_when_used_as_watermark_then_compile_succeeds(
    tmp_path: Path, adapter: DuckDbAdapter, test_case: UncappedWatermarkChainTestCase
) -> None:
    result: CompilePipelineResult = compile_capped_dependency_project(
        project_dir=tmp_path,
        adapter=adapter,
        action=None,
        consumer_sql=capped_dependency_consumer_sql(
            watermark_mode="all", input_name=test_case.watermark_input_name
        ),
        intermediary_names=test_case.intermediary_names,
    )

    assert (
        tuple(entry.name for entry in result.plan_output.model_entries)
        == test_case.expected_model_names
    )


@pytest.mark.parametrize(
    "test_case",
    (
        CappedIntermediateFilterTestCase(
            description="capped input is filter-only on microbatch intermediary",
            expected_model_names=(
                "capped_events",
                "intermediate_events",
                "downstream_events",
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_capped_filter_input_on_intermediate_when_downstream_watermarks_then_compile_succeeds(
    tmp_path: Path, adapter: DuckDbAdapter, test_case: CappedIntermediateFilterTestCase
) -> None:
    result: CompilePipelineResult = compile_capped_microbatch_intermediary_project(
        project_dir=tmp_path,
        adapter=adapter,
        input_role="filter",
    )

    assert (
        tuple(entry.name for entry in result.plan_output.model_entries)
        == test_case.expected_model_names
    )


@pytest.mark.parametrize(
    "test_case",
    (
        CappedIntermediateWatermarkTestCase(
            description="capped input is watermark on microbatch intermediary",
            expected_error_fragment=(
                "model 'intermediate_events' uses capped producer 'capped_events' as a watermark "
                "input; capped producers cannot serve as watermark inputs"
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_capped_watermark_on_intermediate_when_compiling_then_rejects_edge(
    tmp_path: Path, adapter: DuckDbAdapter, test_case: CappedIntermediateWatermarkTestCase
) -> None:
    with pytest.raises(CompileInputError, match=test_case.expected_error_fragment):
        compile_capped_microbatch_intermediary_project(
            project_dir=tmp_path,
            adapter=adapter,
            input_role="watermark",
        )


@pytest.mark.parametrize(
    "test_case",
    (
        PlainCappedConsumerTestCase(
            description="view consumer",
            materialized="view",
            expected_model_names=("capped_events", "downstream_events"),
        ),
        PlainCappedConsumerTestCase(
            description="table consumer",
            materialized="table",
            expected_model_names=("capped_events", "downstream_events"),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_capped_producer_when_used_by_plain_model_then_compile_succeeds(
    tmp_path: Path, adapter: DuckDbAdapter, test_case: PlainCappedConsumerTestCase
) -> None:
    result: CompilePipelineResult = compile_capped_dependency_project(
        project_dir=tmp_path,
        adapter=adapter,
        action=MicrobatchLimitAction.CAP_FROM_START,
        consumer_sql=plain_capped_consumer_sql(materialized=test_case.materialized),
    )

    assert (
        tuple(entry.name for entry in result.plan_output.model_entries)
        == test_case.expected_model_names
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
