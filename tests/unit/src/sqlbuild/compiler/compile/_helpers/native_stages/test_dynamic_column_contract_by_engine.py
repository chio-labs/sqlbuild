"""A model's native analysis may carry its dynamic pivot proof; otherwise Python proves it."""

from __future__ import annotations

from functools import partial

import pytest

from sqlbuild.compiler.compile._helpers.analysis.dynamic_pivot import (
    analyze_dynamic_column_contract,
)
from sqlbuild.compiler.compile._helpers.native_stages.assembly import (
    dynamic_column_contract_by_engine,
)
from sqlbuild.compiler.compile.models import (
    DynamicColumnContractProof,
    ModelSqlAnalysis,
    PolyglotAnalysisResult,
)
from sqlbuild.spec.contracts.models import SchemaDynamicColumnFamily
from tests.unit.src.sqlbuild.compiler.compile._helpers.native_stages._test_types import (
    DynamicColumnContractDispatchTestCase,
)

_NATIVE_PROOF: DynamicColumnContractProof = DynamicColumnContractProof(
    output_proven=False, failure_reason="native session proof"
)
_PYTHON_UNSUPPORTED_PROOF: DynamicColumnContractProof = DynamicColumnContractProof(
    output_proven=False,
    failure_reason=("adapter dialect 'bigquery' does not support compiler-proven dynamic pivots"),
)
_FAMILY: SchemaDynamicColumnFamily = SchemaDynamicColumnFamily(
    name="category_amounts",
    pivot_column="category",
    value_column="amount",
    aggregate="MAX",
    type="DECIMAL(12,2)",
)
_ANALYSIS: PolyglotAnalysisResult = PolyglotAnalysisResult(analysis_succeeded=True)


@pytest.mark.parametrize(
    "test_case",
    (
        DynamicColumnContractDispatchTestCase(
            description="native analysis proof replaces the python proof",
            native_proof=None,
            sql_analysis=ModelSqlAnalysis(
                polyglot_analysis=_ANALYSIS,
                placeholders=None,
                dynamic_column_contract=_NATIVE_PROOF,
            ),
            dialect="bigquery",
            families=(_FAMILY,),
            expected_proof=_NATIVE_PROOF,
        ),
        DynamicColumnContractDispatchTestCase(
            description="analysis without a proof falls back to the python proof",
            native_proof=None,
            sql_analysis=ModelSqlAnalysis(polyglot_analysis=_ANALYSIS, placeholders=None),
            dialect="bigquery",
            families=(_FAMILY,),
            expected_proof=_PYTHON_UNSUPPORTED_PROOF,
        ),
        DynamicColumnContractDispatchTestCase(
            description="unanalyzed model falls back to the python proof",
            native_proof=None,
            sql_analysis=None,
            dialect="bigquery",
            families=(_FAMILY,),
            expected_proof=_PYTHON_UNSUPPORTED_PROOF,
        ),
        DynamicColumnContractDispatchTestCase(
            description="a batched native proof answers an unanalyzed model",
            native_proof=_NATIVE_PROOF,
            sql_analysis=None,
            dialect="bigquery",
            families=(_FAMILY,),
            expected_proof=_NATIVE_PROOF,
        ),
        DynamicColumnContractDispatchTestCase(
            description="model without dynamic families has no proof",
            native_proof=None,
            sql_analysis=ModelSqlAnalysis(polyglot_analysis=_ANALYSIS, placeholders=None),
            dialect="snowflake",
            families=(),
            expected_proof=None,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_model_analysis_when_proving_dynamic_contract_then_native_proof_takes_precedence(
    test_case: DynamicColumnContractDispatchTestCase,
) -> None:
    proof: DynamicColumnContractProof | None = dynamic_column_contract_by_engine(
        sql_analysis=test_case.sql_analysis,
        native_proof=test_case.native_proof,
        python_proof=partial(
            analyze_dynamic_column_contract,
            query_sql="SELECT * FROM order_amounts",
            dialect=test_case.dialect,
            families=test_case.families,
            column_types_by_table={},
            authoritative_column_types_by_table={},
            column_nullability_by_table={},
            dynamic_families_by_table={},
        ),
    )

    assert proof == test_case.expected_proof


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
