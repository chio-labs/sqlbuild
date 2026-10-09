from __future__ import annotations

import pytest

from sqlbuild.compiler.compile._helpers.render.templating import (
    expand_effective_vars,
    expand_template_data,
)
from sqlbuild.compiler.compile.classes.unicode_environment import UnicodeEnvironment
from sqlbuild.compiler.compile.exceptions import CompileInputError
from tests.unit.src.sqlbuild.compiler.compile._helpers._test_types import (
    ExpandTemplateDataErrorTestCase,
    ExpandTemplateDataTestCase,
    UndecodableSecretTestCase,
)

_SECRET: str = "warehouse-pass-7f3a"


@pytest.mark.parametrize(
    "test_case",
    [
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
            value="${if(eq(CTX:run.target, 'prod'), 'warehouse', 'scratch')}",
            variables={},
            context_values={"run.target": "prod"},
            context_label="model config",
            allow_context=True,
            preserve_context_tokens=False,
            preserve_unknown_context=False,
            expected_value="warehouse",
        ),
        ExpandTemplateDataTestCase(
            description="ne chooses else branch when values match",
            value="${if(ne(CTX:run.target, 'prod'), 'scratch', 'warehouse')}",
            variables={},
            context_values={"run.target": "prod"},
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
        ExpandTemplateDataTestCase(
            description="embedded expression stringifies null variable as empty string",
            value="schema_${optional_suffix}",
            variables={"optional_suffix": None},
            context_values={},
            context_label="model config",
            allow_context=False,
            preserve_context_tokens=False,
            preserve_unknown_context=False,
            expected_value="schema_",
        ),
        ExpandTemplateDataTestCase(
            description="full template preserves structured variable value",
            value="${grants}",
            variables={"grants": {"role": "analyst"}},
            context_values={},
            context_label="model config",
            allow_context=False,
            preserve_context_tokens=False,
            preserve_unknown_context=False,
            expected_value={"role": "analyst"},
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_template_expressions_when_expanding_then_returns_expected_value(
    test_case: ExpandTemplateDataTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CI", "1")
    monkeypatch.setenv("APPEND_INCLUSIVE", "0")
    monkeypatch.delenv("CUSTOM_SCHEMA", raising=False)

    result: object = expand_template_data(
        value=test_case.value,
        variables=test_case.variables,
        context_values=test_case.context_values,
        context_label=test_case.context_label,
        allow_context=test_case.allow_context,
        preserve_context_tokens=test_case.preserve_context_tokens,
        preserve_unknown_context=test_case.preserve_unknown_context,
    )

    assert result == test_case.expected_value


@pytest.mark.parametrize(
    "test_case",
    [
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
        ExpandTemplateDataErrorTestCase(
            description="embedded structured variable raises clear error",
            value="schema_${grants}",
            variables={"grants": {"role": "analyst"}},
            context_values={},
            context_label="model config",
            allow_context=False,
            preserve_context_tokens=False,
            preserve_unknown_context=False,
            expected_error_fragment=(
                r"model config variable 'grants' is an object and cannot be interpolated "
                r'as text: \{"role":"analyst"\}. Use a macro to consume structured vars\.'
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_template_expressions_when_expanding_then_raises_clear_error(
    test_case: ExpandTemplateDataErrorTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CI", "1")

    with pytest.raises(CompileInputError, match=test_case.expected_error_fragment):
        expand_template_data(
            value=test_case.value,
            variables=test_case.variables,
            context_values=test_case.context_values,
            context_label=test_case.context_label,
            allow_context=test_case.allow_context,
            preserve_context_tokens=test_case.preserve_context_tokens,
            preserve_unknown_context=test_case.preserve_unknown_context,
        )


@pytest.mark.parametrize(
    "test_case",
    [
        UndecodableSecretTestCase(
            description="undecodable byte after the secret",
            value=f"{_SECRET}\udcff",
            secret=_SECRET,
            expected_message=(
                "Environment variable 'SQB_ORDERS_PASSWORD' is not valid UTF-8 text: byte 19 "
                "starts an invalid UTF-8 sequence"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_undecodable_env_value_when_reading_then_error_never_shows_the_value(
    test_case: UndecodableSecretTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SQB_ORDERS_PASSWORD", str(test_case.value))

    with pytest.raises(CompileInputError) as raised:
        _ = UnicodeEnvironment()["SQB_ORDERS_PASSWORD"]

    assert (
        raised.value.message,
        test_case.secret in f"{raised.value.message} {raised.value.help}",
    ) == (test_case.expected_message, False)


@pytest.mark.parametrize(
    "test_case",
    [
        UndecodableSecretTestCase(
            description="top-level text",
            value=f"{_SECRET}\ud800",
            secret=_SECRET,
            expected_message=(
                "Variable 'orders_password' holds a lone surrogate in its value at UTF-8 byte "
                "19, which is not valid Unicode text"
            ),
        ),
        UndecodableSecretTestCase(
            description="nested list item",
            value={"credentials": [_SECRET, f"{_SECRET}\udcff"]},
            secret=_SECRET,
            expected_message=(
                "Variable 'orders_password' holds a lone surrogate in its value['credentials'][1] "
                "at UTF-8 byte 19, which is not valid Unicode text"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_lone_surrogate_var_when_expanding_then_error_never_shows_the_value(
    test_case: UndecodableSecretTestCase,
) -> None:
    with pytest.raises(CompileInputError) as raised:
        expand_effective_vars({"orders_password": test_case.value})

    assert (
        raised.value.message,
        test_case.secret in f"{raised.value.message} {raised.value.help}",
    ) == (test_case.expected_message, False)
