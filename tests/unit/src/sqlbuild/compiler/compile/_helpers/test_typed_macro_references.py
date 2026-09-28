from __future__ import annotations

import re
from pathlib import Path

import pytest

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import CompilerDiagnostic
from tests.unit.src.sqlbuild.compiler.compile._helpers._test_types import (
    MacroGeneratedReferenceCollectionTestCase,
    MacroGeneratedReferenceErrorTestCase,
    MacroGeneratedReferenceSwitchTestCase,
    MalformedTypedMacroReferenceTestCase,
    TypedMacroReferenceTestCase,
    TypedReferenceAdapterRenderingTestCase,
)
from tests.unit.src.sqlbuild.compiler.compile._helpers.helpers import (
    collect_typed_macro_violations,
    expand_typed_macro_sql,
    resolve_model_references_for_adapter,
)

_UNION_MACRO: str = (
    "def union_all(relations):\n"
    "    return ' UNION ALL '.join(f'SELECT order_id FROM {relation}' for relation in relations)\n"
)
_BASE_MACRO: str = "def base(relation):\n    return f'SELECT * FROM {relation}'\n"
_EMITTING_MACRO: str = "def orders_base():\n    return 'SELECT * FROM __ref(\"stg_orders\")'\n"


@pytest.mark.parametrize(
    "test_case",
    [
        TypedMacroReferenceTestCase(
            description="single model reference renders as the call-site reference",
            macro_file_contents=_BASE_MACRO,
            sql='@base(__ref("orders"))',
            expected_sql='SELECT * FROM __ref("orders")',
        ),
        TypedMacroReferenceTestCase(
            description="references inside a list render in order",
            macro_file_contents=_UNION_MACRO,
            sql='@union_all([__ref("orders_eu"), __ref("orders_us")])',
            expected_sql=(
                'SELECT order_id FROM __ref("orders_eu") UNION ALL '
                'SELECT order_id FROM __ref("orders_us")'
            ),
        ),
        TypedMacroReferenceTestCase(
            description="references inside a dictionary and keyword arguments",
            macro_file_contents=(
                "def pick(relations, key):\n    return f'SELECT * FROM {relations[key]}'\n"
            ),
            sql='@pick(relations={"eu": __ref("orders_eu"), "us": __ref("orders_us")}, key="us")',
            expected_sql='SELECT * FROM __ref("orders_us")',
        ),
        TypedMacroReferenceTestCase(
            description="source and seed references keep their kind",
            macro_file_contents=(
                "def join_lookup(orders, countries):\n"
                "    return f'SELECT * FROM {orders} JOIN {countries} USING (country_code)'\n"
            ),
            sql='@join_lookup(__source("raw_orders"), __seed("country_codes"))',
            expected_sql=(
                'SELECT * FROM __source("raw_orders") JOIN __seed("country_codes") '
                "USING (country_code)"
            ),
        ),
        TypedMacroReferenceTestCase(
            description="macro receives typed values it can inspect",
            macro_file_contents=(
                "from sqlbuild.refs import SqlResourceRef, SqlResourceRefKind\n\n"
                "def describe(relation):\n"
                "    assert isinstance(relation, SqlResourceRef)\n"
                "    assert relation.kind is SqlResourceRefKind.SEED\n"
                "    return f\"SELECT '{relation.name}' AS seed_name FROM {relation}\"\n"
            ),
            sql='@describe(__seed("country_codes"))',
            expected_sql="SELECT 'country_codes' AS seed_name FROM __seed(\"country_codes\")",
        ),
        TypedMacroReferenceTestCase(
            description="nested macro output carrying a reference renders once at the top level",
            macro_file_contents=(
                f"{_BASE_MACRO}\n"
                "def wrap(sql):\n    return f'SELECT order_id FROM ({sql}) AS wrapped'\n"
            ),
            sql='@wrap(@base(__ref("orders")))',
            expected_sql='SELECT order_id FROM (SELECT * FROM __ref("orders")) AS wrapped',
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_typed_reference_arguments_when_expanding_then_renders_call_site_references(
    test_case: TypedMacroReferenceTestCase, tmp_path: Path
) -> None:
    expanded: str = expand_typed_macro_sql(
        tmp_path=tmp_path, macro_file_contents=test_case.macro_file_contents, sql=test_case.sql
    )

    assert expanded == test_case.expected_sql


@pytest.mark.parametrize(
    "test_case",
    [
        MacroGeneratedReferenceErrorTestCase(
            description="macro code that emits a model reference",
            macro_file_contents=_EMITTING_MACRO,
            sql="@orders_base()",
            expected_error_fragments=(
                "model:order_summary depends on model:stg_orders through macro orders_base()",
                "--> macros/common.py",
                'pass it in: @orders_base(__ref("stg_orders"))',
                "[references] enforce_explicit = false",
            ),
        ),
        MacroGeneratedReferenceErrorTestCase(
            description="quoted string argument smuggling a reference",
            macro_file_contents="def wrap(sql):\n    return f'SELECT * FROM ({sql})'\n",
            sql="@wrap('__ref(\"stg_orders\")')",
            expected_error_fragments=(
                "model:order_summary depends on model:stg_orders through macro wrap()",
                "[references] enforce_explicit = false",
            ),
        ),
        MacroGeneratedReferenceErrorTestCase(
            description="macro code that emits a source reference",
            macro_file_contents=(
                "def raw_orders():\n    return 'SELECT * FROM __source(\"raw_orders\")'\n"
            ),
            sql="@raw_orders()",
            expected_error_fragments=("depends on source:raw_orders through macro raw_orders()",),
        ),
        MacroGeneratedReferenceErrorTestCase(
            description="nested macro that emits a seed reference",
            macro_file_contents=(
                "def countries():\n    return '__seed(\"country_codes\")'\n\n"
                "def wrap(sql):\n    return f'SELECT * FROM {sql}'\n"
            ),
            sql="@wrap(@countries())",
            expected_error_fragments=("depends on seed:country_codes through macro countries()",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_macro_output_reference_when_expanding_then_raises_explicit_reference_error(
    test_case: MacroGeneratedReferenceErrorTestCase, tmp_path: Path
) -> None:
    with pytest.raises(CompileInputError) as error:
        expand_typed_macro_sql(
            tmp_path=tmp_path, macro_file_contents=test_case.macro_file_contents, sql=test_case.sql
        )

    assert error.value.code == "P006"
    rendered: str = f"{error.value.message}\n{error.value.help}"
    assert all(fragment in rendered for fragment in test_case.expected_error_fragments)


@pytest.mark.parametrize(
    "test_case",
    [
        MacroGeneratedReferenceCollectionTestCase(
            description="every emitted reference is reported once, in order",
            macro_file_contents=(
                "def pair():\n"
                '    return \'SELECT * FROM __ref("stg_orders") JOIN __seed("country_codes") ON 1\'\n\n'
                "def raw_orders():\n    return 'SELECT * FROM __source(\"raw_orders\")'\n"
            ),
            sql="@pair() UNION ALL @pair() UNION ALL @raw_orders()",
            expected_messages=(
                "model:order_summary depends on model:stg_orders through macro pair()",
                "model:order_summary depends on seed:country_codes through macro pair()",
                "model:order_summary depends on source:raw_orders through macro raw_orders()",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_several_macro_output_references_when_collecting_then_reports_each_once(
    test_case: MacroGeneratedReferenceCollectionTestCase, tmp_path: Path
) -> None:
    diagnostics: tuple[CompilerDiagnostic, ...] = collect_typed_macro_violations(
        tmp_path=tmp_path, macro_file_contents=test_case.macro_file_contents, sql=test_case.sql
    )

    assert tuple(diagnostic.message for diagnostic in diagnostics) == test_case.expected_messages
    assert {diagnostic.code for diagnostic in diagnostics} == {"P006"}
    assert {diagnostic.resource_name for diagnostic in diagnostics} == {"order_summary"}


@pytest.mark.parametrize(
    "test_case",
    [
        MacroGeneratedReferenceSwitchTestCase(
            description="macro code that emits a model reference",
            macro_file_contents=_EMITTING_MACRO,
            sql="@orders_base()",
            expected_sql='SELECT * FROM __ref("stg_orders")',
        ),
        MacroGeneratedReferenceSwitchTestCase(
            description="quoted string argument smuggling a reference",
            macro_file_contents="def wrap(sql):\n    return f'SELECT * FROM {sql}'\n",
            sql="@wrap('__ref(\"stg_orders\")')",
            expected_sql='SELECT * FROM __ref("stg_orders")',
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_enforcement_disabled_when_macro_emits_reference_then_expands_unchanged(
    test_case: MacroGeneratedReferenceSwitchTestCase, tmp_path: Path
) -> None:
    expanded: str = expand_typed_macro_sql(
        tmp_path=tmp_path,
        macro_file_contents=test_case.macro_file_contents,
        sql=test_case.sql,
        enforce_explicit=False,
    )

    assert expanded == test_case.expected_sql


@pytest.mark.parametrize(
    "test_case",
    [
        MalformedTypedMacroReferenceTestCase(
            description="non-string name",
            sql="@base(__ref(1))",
            expected_error_fragment="must contain exactly one quoted resource name",
        ),
        MalformedTypedMacroReferenceTestCase(
            description="two names",
            sql='@base(__ref("a", "b"))',
            expected_error_fragment="must contain exactly one quoted resource name",
        ),
        MalformedTypedMacroReferenceTestCase(
            description="keyword name",
            sql='@base(__ref(name="a"))',
            expected_error_fragment="must contain exactly one quoted resource name",
        ),
        MalformedTypedMacroReferenceTestCase(
            description="unsupported reference function",
            sql='@base(__udf("a"))',
            expected_error_fragment="__ref(), __source(), or __seed() references",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_malformed_reference_argument_when_expanding_then_raises(
    test_case: MalformedTypedMacroReferenceTestCase, tmp_path: Path
) -> None:
    with pytest.raises(CompileInputError, match=re.escape(test_case.expected_error_fragment)):
        expand_typed_macro_sql(
            tmp_path=tmp_path, macro_file_contents=_BASE_MACRO, sql=test_case.sql
        )


@pytest.mark.parametrize(
    "test_case",
    [
        TypedReferenceAdapterRenderingTestCase(
            description="bigquery",
            adapter_name="bigquery",
            expected_resolved_sql="SELECT * FROM `analytics.sales.orders`",
        ),
        TypedReferenceAdapterRenderingTestCase(
            description="duckdb",
            adapter_name="duckdb",
            expected_resolved_sql="SELECT * FROM analytics.sales.orders",
        ),
        TypedReferenceAdapterRenderingTestCase(
            description="postgres",
            adapter_name="postgres",
            expected_resolved_sql="SELECT * FROM analytics.sales.orders",
        ),
        TypedReferenceAdapterRenderingTestCase(
            description="snowflake",
            adapter_name="snowflake",
            expected_resolved_sql="SELECT * FROM analytics.sales.orders",
        ),
        TypedReferenceAdapterRenderingTestCase(
            description="sqlserver",
            adapter_name="sqlserver",
            expected_resolved_sql="SELECT * FROM analytics.sales.orders",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_adapter_when_resolving_typed_macro_reference_then_uses_adapter_quoting(
    test_case: TypedReferenceAdapterRenderingTestCase, tmp_path: Path
) -> None:
    expanded: str = expand_typed_macro_sql(
        tmp_path=tmp_path, macro_file_contents=_BASE_MACRO, sql='@base(__ref("orders"))'
    )

    resolved: str = resolve_model_references_for_adapter(
        sql=expanded, adapter_name=test_case.adapter_name
    )

    assert resolved == test_case.expected_resolved_sql
