"""Unit tests for the required-description compile check (P010)."""

from __future__ import annotations

import inspect
from dataclasses import asdict, fields
from functools import partial
from pathlib import Path

import pytest

from sqlbuild.compiler.compile.constants import (
    DESCRIPTION_EXEMPT_INPUTS,
    DESCRIPTION_REQUIRED_INPUT_KINDS,
)
from sqlbuild.compiler.compile.models import CompilerDiagnostic
from sqlbuild.compiler.compile.types import FunctionLanguage
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from tests.unit.src.sqlbuild.compiler.compile._helpers._test_types import (
    DescriptionInputClassificationCase,
    RequiredDescriptionLocationCase,
    RequiredDescriptionUnitCase,
)
from tests.unit.src.sqlbuild.compiler.compile._helpers.helpers import (
    UndescribedApi,
    documented_returns_loader,
    function_description_inputs,
    loader_backed_source_description_inputs,
    loader_only_description_inputs,
    model_description_inputs,
    provider_description_inputs,
    refresh_exports_task,
    required_description_diagnostics,
    scenario_description_inputs,
    seed_description_inputs,
    source_description_inputs,
    sql_hook_description_inputs,
    task_description_inputs,
)

_UDF_AFTER_MENTIONS: str = (
    '"""Mentions @udf before the decorator."""\n'
    "# @udf in a comment\n"
    "from sqlbuild.functions import udf\n\n\n"
    '@udf(returns="BOOLEAN")\n'
    "def main(amount: int) -> bool:\n"
    "    return amount > 100\n"
)


CASES: tuple[RequiredDescriptionUnitCase, ...] = (
    RequiredDescriptionUnitCase(
        "model header after a leading comment",
        model_description_inputs,
        "model 'order_totals' has no description",
        ("models/order_totals.sql", 2, 1),
    ),
    RequiredDescriptionUnitCase(
        "scenario header",
        scenario_description_inputs,
        "scenario 'orders__paid' has no description",
        ("tests/scenarios/orders__paid.sql", 2, 1),
    ),
    RequiredDescriptionUnitCase(
        "seed YAML entry",
        seed_description_inputs,
        "seed 'product_types' has no description",
        ("seeds/product_types.yml", 2, 1),
    ),
    RequiredDescriptionUnitCase(
        "source YAML entry among others",
        source_description_inputs,
        "source 'raw_returns' has no description",
        ("sources/raw.yml", 4, 1),
    ),
    RequiredDescriptionUnitCase(
        "source described through its loader",
        loader_backed_source_description_inputs,
        "source 'raw_returns' has no description",
        ("sources/raw.yml", 4, 1),
    ),
    RequiredDescriptionUnitCase(
        "loader without a source declaration",
        loader_only_description_inputs,
        "loader 'raw_returns' has no description",
        ("python/loaders/raw_returns.py", documented_returns_loader.__code__.co_firstlineno, 1),
    ),
    RequiredDescriptionUnitCase(
        "SQL function header",
        function_description_inputs,
        "function 'is_large_order' has no description",
        ("functions/sql/is_large_order.sql", 1, 1),
    ),
    RequiredDescriptionUnitCase(
        "named SQL hook",
        sql_hook_description_inputs,
        "hook 'analyze_orders' has no description",
        ("hooks/sql/analyze_orders.sql", 1, 1),
    ),
    RequiredDescriptionUnitCase(
        "task",
        task_description_inputs,
        "task 'refresh_exports' has no description",
        ("python/tasks/refresh_exports.py", refresh_exports_task.__code__.co_firstlineno, 1),
    ),
    RequiredDescriptionUnitCase(
        "provider",
        provider_description_inputs,
        "provider 'orders_api' has no description",
        ("providers/orders_api.py", inspect.getsourcelines(UndescribedApi)[1], 1),
    ),
)


@pytest.mark.parametrize(
    "test_case",
    [RequiredDescriptionUnitCase(**asdict(case)) for case in CASES],
    ids=lambda case: case.description,
)
def test_given_undescribed_resource_when_checking_then_reports_one_p010_at_declaration(
    test_case: RequiredDescriptionUnitCase,
) -> None:
    diagnostics: tuple[CompilerDiagnostic, ...] = required_description_diagnostics(
        test_case.build(None)
    )

    assert [
        (item.code, item.message, (str(item.path), item.line, item.column)) for item in diagnostics
    ] == [("P010", test_case.expected_message, test_case.expected_location)]


@pytest.mark.parametrize(
    "test_case",
    [RequiredDescriptionUnitCase(**asdict(case)) for case in CASES],
    ids=lambda case: case.description,
)
def test_given_described_resource_when_checking_then_reports_nothing(
    test_case: RequiredDescriptionUnitCase,
) -> None:
    diagnostics: tuple[CompilerDiagnostic, ...] = required_description_diagnostics(
        test_case.build("Described resource.")
    )

    assert test_case.expected_message not in [item.message for item in diagnostics]
    assert diagnostics == ()


@pytest.mark.parametrize(
    "test_case",
    [
        DescriptionInputClassificationCase(
            description="every discovered input field is required or exempt",
            required=frozenset(DESCRIPTION_REQUIRED_INPUT_KINDS),
            exempt=frozenset(DESCRIPTION_EXEMPT_INPUTS),
            expected_fields=frozenset(item.name for item in fields(DiscoveredProjectInputs)),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_discovered_input_fields_when_classifying_then_every_field_is_checked_or_exempt(
    test_case: DescriptionInputClassificationCase,
) -> None:
    assert not test_case.required & test_case.exempt
    assert test_case.required | test_case.exempt == test_case.expected_fields


@pytest.mark.parametrize(
    "test_case",
    [
        RequiredDescriptionLocationCase(
            description="MODEL header after a block comment that mentions MODEL (",
            build=partial(
                model_description_inputs,
                None,
                contents="/*\nMODEL (old)\n*/\n-- note\nMODEL (materialized table);\nSELECT 1\n",
            ),
            expected_location=("models/order_totals.sql", 5, 1),
        ),
        RequiredDescriptionLocationCase(
            description="FUNCTION header after a leading comment",
            build=partial(
                function_description_inputs,
                None,
                contents="-- returns a flag\nFUNCTION (returns BOOLEAN);\n\nTRUE\n",
            ),
            expected_location=("functions/sql/is_large_order.sql", 2, 1),
        ),
        RequiredDescriptionLocationCase(
            description="HOOK header after a leading block comment",
            build=partial(
                sql_hook_description_inputs, None, contents="/* analyze */\nHOOK ();\nSELECT 1\n"
            ),
            expected_location=("hooks/sql/analyze_orders.sql", 2, 1),
        ),
        RequiredDescriptionLocationCase(
            description="SCENARIO header after a leading comment",
            build=partial(
                scenario_description_inputs, None, contents="-- paid\nSCENARIO ();\nSELECT 1\n"
            ),
            expected_location=("tests/scenarios/orders__paid.sql", 2, 1),
        ),
        RequiredDescriptionLocationCase(
            description="@udf decorator after docstring and comment mentions",
            build=partial(
                function_description_inputs,
                None,
                contents=_UDF_AFTER_MENTIONS,
                relative_path=Path("functions/python/is_large_order.py"),
                language=FunctionLanguage.PYTHON,
            ),
            expected_location=("functions/python/is_large_order.py", 6, 1),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_comments_before_declaration_when_checking_then_points_at_declaration(
    test_case: RequiredDescriptionLocationCase,
) -> None:
    diagnostics: tuple[CompilerDiagnostic, ...] = required_description_diagnostics(
        test_case.build()
    )

    assert [(str(item.path), item.line, item.column) for item in diagnostics] == [
        test_case.expected_location
    ]


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
