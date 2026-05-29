from __future__ import annotations

import pytest

from sqlbuild.shared.helpers.cli_style import CliStyle
from tests.unit.src.sqlbuild.shared.helpers._test_types import CliStyleTestCase

TEST_CASES: list[CliStyleTestCase] = [
    CliStyleTestCase(
        description="leaves semantic text unstyled when color is disabled",
        use_color=False,
        expected_title="Title",
        expected_section="Section",
        expected_label="Label",
        expected_value="Value",
        expected_accent="Accent",
        expected_success="Success",
        expected_success_strong="Success strong",
        expected_warning="Warning",
        expected_warning_strong="Warning strong",
        expected_error="Error",
        expected_error_strong="Error strong",
        expected_error_muted="error",
        expected_log_label="log",
        expected_status_ok="OK",
        expected_status_error="ERROR",
        expected_status_skip="SKIP",
        expected_dbt_section="dbt",
        expected_dbt_object_name="analytics.orders",
    ),
    CliStyleTestCase(
        description="applies default semantic colors when color is enabled",
        use_color=True,
        expected_title="\033[32m\033[1mTitle\033[0m",
        expected_section="\033[1mSection\033[0m",
        expected_label="\033[2mLabel\033[0m",
        expected_value="\033[34m\033[1mValue\033[0m",
        expected_accent="\033[34mAccent\033[0m",
        expected_success="\033[32mSuccess\033[0m",
        expected_success_strong="\033[32m\033[1mSuccess strong\033[0m",
        expected_warning="\033[33mWarning\033[0m",
        expected_warning_strong="\033[33m\033[1mWarning strong\033[0m",
        expected_error="\033[31mError\033[0m",
        expected_error_strong="\033[31m\033[1mError strong\033[0m",
        expected_error_muted="\033[31m\033[2merror\033[0m",
        expected_log_label="\033[34m\033[2mlog\033[0m",
        expected_status_ok="\033[32mOK\033[0m",
        expected_status_error="\033[31mERROR\033[0m",
        expected_status_skip="\033[2mSKIP\033[0m",
        expected_dbt_section="\033[38;5;208m\033[1mdbt\033[0m",
        expected_dbt_object_name="\033[38;5;208m\033[1manalytics.orders\033[0m",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
)
def test_given_cli_style_when_rendering_semantic_roles_then_returns_expected_text(
    test_case: CliStyleTestCase,
) -> None:
    style: CliStyle = CliStyle(use_color=test_case.use_color)

    assert style.title("Title") == test_case.expected_title
    assert style.section("Section") == test_case.expected_section
    assert style.label("Label") == test_case.expected_label
    assert style.value("Value") == test_case.expected_value
    assert style.accent("Accent") == test_case.expected_accent
    assert style.success("Success") == test_case.expected_success
    assert style.success_strong("Success strong") == test_case.expected_success_strong
    assert style.warning("Warning") == test_case.expected_warning
    assert style.warning_strong("Warning strong") == test_case.expected_warning_strong
    assert style.error("Error") == test_case.expected_error
    assert style.error_strong("Error strong") == test_case.expected_error_strong
    assert style.error_muted("error") == test_case.expected_error_muted
    assert style.log_label("log") == test_case.expected_log_label
    assert style.status("OK") == test_case.expected_status_ok
    assert style.status("ERROR") == test_case.expected_status_error
    assert style.status("SKIP") == test_case.expected_status_skip
    assert style.dbt_section("dbt") == test_case.expected_dbt_section
    assert style.dbt_object_name("analytics.orders") == test_case.expected_dbt_object_name


@pytest.mark.parametrize(
    "test_case",
    [
        CliStyleTestCase(
            description="styles custom rendered status text by status word",
            use_color=True,
            expected_title="",
            expected_section="",
            expected_label="",
            expected_value="",
            expected_accent="",
            expected_success="",
            expected_success_strong="",
            expected_warning="",
            expected_warning_strong="",
            expected_error="",
            expected_error_strong="",
            expected_error_muted="",
            expected_log_label="",
            expected_status_ok="\033[32m[OK found]\033[0m",
            expected_status_error="\033[31m[ERROR failed]\033[0m",
            expected_status_skip="\033[2m[SKIP blocked]\033[0m",
            expected_dbt_section="",
            expected_dbt_object_name="",
        )
    ],
    ids=["styles custom rendered status text by status word"],
)
def test_given_cli_style_when_rendering_custom_status_text_then_styles_the_full_text(
    test_case: CliStyleTestCase,
) -> None:
    style: CliStyle = CliStyle(use_color=test_case.use_color)

    assert style.status("OK", "[OK found]") == test_case.expected_status_ok
    assert style.status("ERROR", "[ERROR failed]") == test_case.expected_status_error
    assert style.status("SKIP", "[SKIP blocked]") == test_case.expected_status_skip
