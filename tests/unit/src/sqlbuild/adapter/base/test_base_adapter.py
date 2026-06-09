from __future__ import annotations

from typing import ClassVar

import pytest

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.exceptions import AdapterUserError
from sqlbuild.adapter.shared.models import ExpressionInferenceProfile
from sqlbuild.compiler.compile.models.core import FunctionArgument
from sqlbuild.compiler.compile.types import FunctionLanguage
from tests.unit.src.sqlbuild.adapter.base._test_types import (
    BaseAdapterDurableCloneTestCase,
    BaseAdapterExpressionInferenceProfileTestCase,
    BaseAdapterIdentifierLimitTestCase,
    BaseAdapterPythonFunctionSupportTestCase,
    BaseAdapterSqlAnalysisDialectTestCase,
)


class ConcreteBaseAdapter(BaseAdapter):
    def connect(self, config: dict[str, object]) -> object:
        return object()

    def execute(self, connection: object, sql: str) -> object:
        del connection, sql
        return object()

    def close(self, connection: object) -> None:
        del connection


class PostgresLikeBaseAdapter(ConcreteBaseAdapter):
    sql_analysis_dialect_name: ClassVar[str | None] = "postgres"


BASE_ADAPTER_SQLGLOT_DIALECT_TEST_CASES: list[BaseAdapterSqlAnalysisDialectTestCase] = [
    BaseAdapterSqlAnalysisDialectTestCase(
        description="returns none by default",
        expected_sql_analysis_dialect=None,
    ),
    BaseAdapterSqlAnalysisDialectTestCase(
        description="returns class configured dialect",
        expected_sql_analysis_dialect="postgres",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    [
        BaseAdapterPythonFunctionSupportTestCase(
            description="raises clear error for Python UDFs by default",
            expected_error_fragment="does not support Python UDFs",
        )
    ],
    ids=["raises clear error for Python UDFs by default"],
)
def test_given_python_function_when_rendering_with_base_adapter_then_raises_clear_error(
    test_case: BaseAdapterPythonFunctionSupportTestCase,
) -> None:
    adapter: BaseAdapter = ConcreteBaseAdapter()

    with pytest.raises(AdapterUserError) as exc_info:
        adapter.render_create_function(
            destination="main.is_positive_int",
            arguments=(FunctionArgument(name="a_string", type="VARCHAR"),),
            returns="BOOLEAN",
            body_sql="def main(a_string): return True",
            language=FunctionLanguage.PYTHON,
            runtime_version="3.11",
            entry_point="main",
        )

    assert test_case.expected_error_fragment in str(exc_info.value)


@pytest.mark.parametrize(
    "test_case",
    [
        BaseAdapterExpressionInferenceProfileTestCase(
            description="returns portable inference profile by default",
            expected_sql_analysis_dialect=None,
            expected_function_rules_count=0,
        )
    ],
    ids=["returns portable inference profile by default"],
)
def test_given_base_adapter_when_getting_inference_profile_then_returns_portable_defaults(
    test_case: BaseAdapterExpressionInferenceProfileTestCase,
) -> None:
    adapter: BaseAdapter = ConcreteBaseAdapter()

    profile: ExpressionInferenceProfile = adapter.expression_inference_profile()

    assert profile.sql_analysis_dialect == test_case.expected_sql_analysis_dialect
    assert len(profile.function_nullability_rules) == test_case.expected_function_rules_count


@pytest.mark.parametrize(
    "test_case",
    BASE_ADAPTER_SQLGLOT_DIALECT_TEST_CASES,
    ids=[case.description for case in BASE_ADAPTER_SQLGLOT_DIALECT_TEST_CASES],
)
def test_given_base_adapter_subclass_when_getting_sql_analysis_dialect_then_uses_class_setting(
    test_case: BaseAdapterSqlAnalysisDialectTestCase,
) -> None:
    adapter: BaseAdapter = (
        PostgresLikeBaseAdapter()
        if test_case.expected_sql_analysis_dialect is not None
        else ConcreteBaseAdapter()
    )

    assert adapter.sql_analysis_dialect() == test_case.expected_sql_analysis_dialect
    assert adapter.expression_inference_profile().sql_analysis_dialect == (
        test_case.expected_sql_analysis_dialect
    )


@pytest.mark.parametrize(
    "test_case",
    [
        BaseAdapterIdentifierLimitTestCase(
            description="returns postgres-compatible identifier limit by default",
            expected_identifier_limit=63,
        )
    ],
    ids=["returns postgres-compatible identifier limit by default"],
)
def test_given_base_adapter_when_getting_identifier_limit_then_returns_portable_default(
    test_case: BaseAdapterIdentifierLimitTestCase,
) -> None:
    adapter: BaseAdapter = ConcreteBaseAdapter()

    assert adapter.maximum_identifier_length() == test_case.expected_identifier_limit


@pytest.mark.parametrize(
    "test_case",
    [
        BaseAdapterDurableCloneTestCase(
            description="renders durable clone as CTAS fallback by default",
            source="prod.fact_orders",
            target="dev.fact_orders",
            expected_supports_durable_clone=False,
            expected_statements=(
                "CREATE OR REPLACE TABLE dev.fact_orders AS SELECT * FROM prod.fact_orders",
            ),
        )
    ],
    ids=["renders durable clone as CTAS fallback by default"],
)
def test_given_base_adapter_when_rendering_durable_clone_then_uses_copy_fallback(
    test_case: BaseAdapterDurableCloneTestCase,
) -> None:
    adapter: BaseAdapter = ConcreteBaseAdapter()

    result: tuple[str, ...] = adapter.render_durable_clone(
        origin=test_case.source,
        destination=test_case.target,
    )

    assert adapter.supports_durable_clone() is test_case.expected_supports_durable_clone
    assert result == test_case.expected_statements
