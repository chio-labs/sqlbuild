from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.helpers.templating import expand_template_data
from tests.unit.src.sqlbuild.compiler.compile.helpers._test_types import (
    ExpandTemplateDataErrorTestCase,
    ExpandTemplateDataTestCase,
)

TEST_CASES: list[ExpandTemplateDataTestCase] = [
    ExpandTemplateDataTestCase(
        description="if uses truthy env flag",
        value="${if(ENV:CI, 'ci_schema', 'dev_schema')}",
        variables={},
        context_values={},
        context_label="model config",
        allow_context=False,
        preserve_context_tokens=False,
        preserve_unknown_context=False,
        expected_value="ci_schema",
    ),
    ExpandTemplateDataTestCase(
        description="if can return typed bool for full template value",
        value="${if(eq(ENV:APPEND_INCLUSIVE, '0'), false, true)}",
        variables={},
        context_values={},
        context_label="model config",
        allow_context=False,
        preserve_context_tokens=False,
        preserve_unknown_context=False,
        expected_value=False,
    ),
    ExpandTemplateDataTestCase(
        description="eq compares evaluated references",
        value="${if(eq(CTX:run.environment, 'prod'), 'warehouse', 'scratch')}",
        variables={},
        context_values={"run.environment": "prod"},
        context_label="model config",
        allow_context=True,
        preserve_context_tokens=False,
        preserve_unknown_context=False,
        expected_value="warehouse",
    ),
    ExpandTemplateDataTestCase(
        description="ne chooses else branch when values match",
        value="${if(ne(CTX:run.environment, 'prod'), 'scratch', 'warehouse')}",
        variables={},
        context_values={"run.environment": "prod"},
        context_label="model config",
        allow_context=True,
        preserve_context_tokens=False,
        preserve_unknown_context=False,
        expected_value="warehouse",
    ),
    ExpandTemplateDataTestCase(
        description="coalesce falls back to variable then hardcoded default",
        value="${coalesce(ENV:CUSTOM_SCHEMA, schema_name, 'default_schema')}",
        variables={"schema_name": "analytics"},
        context_values={},
        context_label="model config",
        allow_context=False,
        preserve_context_tokens=False,
        preserve_unknown_context=False,
        expected_value="analytics",
    ),
    ExpandTemplateDataTestCase(
        description="if lazily skips unknown context in unselected branch",
        value="${if(true, 'ok', CTX:missing)}",
        variables={},
        context_values={},
        context_label="model config",
        allow_context=True,
        preserve_context_tokens=False,
        preserve_unknown_context=False,
        expected_value="ok",
    ),
    ExpandTemplateDataTestCase(
        description="embedded expression stringifies bool result",
        value="flag=${eq(ENV:CI, '1')}",
        variables={},
        context_values={},
        context_label="model config",
        allow_context=False,
        preserve_context_tokens=False,
        preserve_unknown_context=False,
        expected_value="flag=true",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
)
def test_given_template_expressions_when_expanding_then_returns_expected_value(
    test_case: ExpandTemplateDataTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CI", "1")
    monkeypatch.setenv("APPEND_INCLUSIVE", "0")
    monkeypatch.delenv("CUSTOM_SCHEMA", raising=False)

    result: object = expand_template_data(
        test_case.value,
        variables=test_case.variables,
        context_values=test_case.context_values,
        context_label=test_case.context_label,
        allow_context=test_case.allow_context,
        preserve_context_tokens=test_case.preserve_context_tokens,
        preserve_unknown_context=test_case.preserve_unknown_context,
    )

    assert result == test_case.expected_value


ERROR_TEST_CASES: list[ExpandTemplateDataErrorTestCase] = [
    ExpandTemplateDataErrorTestCase(
        description="unknown function raises clear error",
        value="${equals(ENV:CI, '1')}",
        variables={},
        context_values={},
        context_label="model config",
        allow_context=False,
        preserve_context_tokens=False,
        preserve_unknown_context=False,
        expected_error_fragment="unsupported template function 'equals'",
    ),
    ExpandTemplateDataErrorTestCase(
        description="if validates argument count",
        value="${if(ENV:CI, 'ci_only')}",
        variables={},
        context_values={},
        context_label="model config",
        allow_context=False,
        preserve_context_tokens=False,
        preserve_unknown_context=False,
        expected_error_fragment=r"if\(\.\.\.\) expects 3 arguments",
    ),
    ExpandTemplateDataErrorTestCase(
        description="coalesce requires at least one argument",
        value="${coalesce()}",
        variables={},
        context_values={},
        context_label="model config",
        allow_context=False,
        preserve_context_tokens=False,
        preserve_unknown_context=False,
        expected_error_fragment=r"coalesce\(\.\.\.\) expects at least 1 argument",
    ),
    ExpandTemplateDataErrorTestCase(
        description="unterminated string raises clear error",
        value="${if(true, 'open, 'closed')}",
        variables={},
        context_values={},
        context_label="model config",
        allow_context=False,
        preserve_context_tokens=False,
        preserve_unknown_context=False,
        expected_error_fragment="unterminated single-quoted string",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    ERROR_TEST_CASES,
    ids=[case.description for case in ERROR_TEST_CASES],
)
def test_given_invalid_template_expressions_when_expanding_then_raises_clear_error(
    test_case: ExpandTemplateDataErrorTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CI", "1")

    with pytest.raises(CompileInputError, match=test_case.expected_error_fragment):
        expand_template_data(
            test_case.value,
            variables=test_case.variables,
            context_values=test_case.context_values,
            context_label=test_case.context_label,
            allow_context=test_case.allow_context,
            preserve_context_tokens=test_case.preserve_context_tokens,
            preserve_unknown_context=test_case.preserve_unknown_context,
        )
