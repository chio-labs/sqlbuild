"""A stored analysis is served only while its inputs and its parents' final signatures match."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.classes.stored_model_analyses import StoredModelAnalyses
from sqlbuild.compiler.compile.models import (
    ModelSqlAnalysisRequest,
    PolyglotAnalysisResult,
    StoredModelAnalysis,
)
from tests.unit.src.sqlbuild.compiler.compile.classes._test_types import (
    StaleServedAnalysisTestCase,
    StoredAnalysisScopeTestCase,
)
from tests.unit.src.sqlbuild.compiler.compile.classes.helpers import (
    RAW_ORDERS_TYPES,
    RecordingAnalysisReuse,
    analysis_request,
    analyzed_model,
    orders_analysis_context,
    orders_stored_analyses,
    stored_analysis,
)

_CHAIN: tuple[ModelSqlAnalysisRequest, ...] = (
    analysis_request(analyzed_model("stg_orders"), "stg_orders-key"),
    analysis_request(analyzed_model("int_orders", "stg_orders"), "int_orders-key"),
    analysis_request(analyzed_model("fct_orders", "int_orders"), "fct_orders-key"),
)
_CHAIN_DEPENDENCIES: dict[str, dict[str, str]] = {
    "stg_orders": {},
    "int_orders": {"stg_orders": "stg_orders-signature"},
    "fct_orders": {"int_orders": "int_orders-signature"},
}
_STORED_SIGNATURES: dict[str, str] = {
    "stg_orders": "stg_orders-signature",
    "int_orders": "int_orders-signature",
    "fct_orders": "fct_orders-signature",
}
_ALL_MODELS: frozenset[str] = frozenset(_CHAIN_DEPENDENCIES)


@pytest.mark.parametrize(
    "test_case",
    [
        StoredAnalysisScopeTestCase(
            description="nothing_changed",
            reused_models=_ALL_MODELS,
            rekeyed_models=frozenset(),
            twinned_models=frozenset(),
            stored_column_types=RAW_ORDERS_TYPES,
            expected_served=_ALL_MODELS,
        ),
        StoredAnalysisScopeTestCase(
            description="root_edited",
            reused_models=frozenset({"int_orders", "fct_orders"}),
            rekeyed_models=frozenset(),
            twinned_models=frozenset(),
            stored_column_types=RAW_ORDERS_TYPES,
            expected_served=frozenset({"int_orders", "fct_orders"}),
        ),
        StoredAnalysisScopeTestCase(
            description="cache_key_changed",
            reused_models=_ALL_MODELS,
            rekeyed_models=frozenset({"int_orders"}),
            twinned_models=frozenset(),
            stored_column_types=RAW_ORDERS_TYPES,
            expected_served=frozenset({"stg_orders", "fct_orders"}),
        ),
        StoredAnalysisScopeTestCase(
            description="cache_key_shared_with_another_model",
            reused_models=_ALL_MODELS,
            rekeyed_models=frozenset(),
            twinned_models=frozenset({"fct_orders"}),
            stored_column_types=RAW_ORDERS_TYPES,
            expected_served=frozenset({"stg_orders", "int_orders"}),
        ),
        StoredAnalysisScopeTestCase(
            description="source_types_changed",
            reused_models=_ALL_MODELS,
            rekeyed_models=frozenset(),
            twinned_models=frozenset(),
            stored_column_types={"raw_orders": {"order_id": "BIGINT"}},
            expected_served=frozenset(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_stored_analyses_when_scoping_reuse_then_only_identical_inputs_are_served(
    test_case: StoredAnalysisScopeTestCase,
) -> None:
    context: str = orders_analysis_context(
        requests=_CHAIN, column_types=test_case.stored_column_types
    )
    stored: dict[str, StoredModelAnalysis] = {
        name: stored_analysis(name=name, context=context, dependencies=dependencies)
        for name, dependencies in _CHAIN_DEPENDENCIES.items()
    }
    requests: tuple[ModelSqlAnalysisRequest, ...] = tuple(
        analysis_request(
            request.model_input,
            f"{request.model_input.model_file.file_path.stem}-key"
            + "-edited"
            * (request.model_input.model_file.file_path.stem in test_case.rekeyed_models),
        )
        for request in _CHAIN
    ) + tuple(
        analysis_request(analyzed_model(f"{name}_twin", "int_orders"), f"{name}-key")
        for name in sorted(test_case.twinned_models)
    )

    served: StoredModelAnalyses = orders_stored_analyses(
        requests=requests,
        reuse=RecordingAnalysisReuse(reused=test_case.reused_models, stored=stored),
    )

    assert frozenset(served.served) == test_case.expected_served


@pytest.mark.parametrize(
    "test_case",
    [
        StaleServedAnalysisTestCase(
            description="parents_unchanged",
            current_signatures=_STORED_SIGNATURES,
            expected_stale=set(),
        ),
        StaleServedAnalysisTestCase(
            description="root_signature_changed",
            current_signatures={**_STORED_SIGNATURES, "stg_orders": "stg_orders-widened"},
            expected_stale={"int_orders"},
        ),
        StaleServedAnalysisTestCase(
            description="middle_signature_changed",
            current_signatures={**_STORED_SIGNATURES, "int_orders": "int_orders-widened"},
            expected_stale={"fct_orders"},
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_served_analyses_when_parents_are_final_then_changed_parents_make_children_stale(
    test_case: StaleServedAnalysisTestCase,
) -> None:
    context: str = orders_analysis_context(requests=_CHAIN, column_types=RAW_ORDERS_TYPES)
    stored: dict[str, StoredModelAnalysis] = {
        name: stored_analysis(name=name, context=context, dependencies=dependencies)
        for name, dependencies in _CHAIN_DEPENDENCIES.items()
    }
    served: StoredModelAnalyses = orders_stored_analyses(
        requests=_CHAIN, reuse=RecordingAnalysisReuse(reused=_ALL_MODELS, stored=stored)
    )
    cached: dict[str, PolyglotAnalysisResult] = {
        analysis.cache_key: analysis.analysis for analysis in stored.values()
    }

    stale: set[str] = served.stale_names(
        requests=_CHAIN, cached=cached, current_signatures=test_case.current_signatures
    )

    assert stale == test_case.expected_stale


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-n", "auto", "--dist", "loadfile"]))
