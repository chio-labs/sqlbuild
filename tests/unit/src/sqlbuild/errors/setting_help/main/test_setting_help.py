from __future__ import annotations

from pathlib import Path

import pytest

from scripts.setting_help.main.find_settings_without_snippet import find_settings_without_snippet
from scripts.setting_help.main.parse_setting_snippet import parse_setting_snippet
from sqlbuild.compiler.compile._helpers.analysis.validation import sql_analysis_opt_out_help
from sqlbuild.compiler.discovery.main.explicit_references_help import explicit_references_help
from sqlbuild.compiler.discovery.main.microbatch_guidance import (
    microbatch_guidance,
)
from sqlbuild.errors.setting_help.main.join_helps import join_helps
from sqlbuild.errors.setting_help.main.model_header_help import model_header_help
from sqlbuild.errors.setting_help.main.setting_help import setting_help
from sqlbuild.errors.setting_help.main.setting_note import setting_note
from tests.unit.src.sqlbuild.errors.setting_help.main._test_types import (
    SettingCatalogueTestCase,
    SettingHelpTestCase,
    SettingSnippetTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (
        SettingHelpTestCase(
            "a boolean setting renders file, section and key",
            setting_help(
                purpose="to allow it",
                file_name="sqlbuild_project.toml",
                section="settings",
                key="require_sql_analysis",
                value=False,
            ),
            "to allow it, set this in sqlbuild_project.toml:\n"
            "            [settings]\n"
            "            require_sql_analysis = false",
        ),
        SettingHelpTestCase(
            "a string setting is quoted",
            setting_help(
                purpose="to stage",
                file_name="sqlbuild_project.toml",
                section="settings",
                key="table_promotion_mode",
                value="staged",
            ),
            "to stage, set this in sqlbuild_project.toml:\n            [settings]\n"
            '            table_promotion_mode = "staged"',
        ),
        SettingHelpTestCase(
            "an explicit note states the current value",
            setting_note(
                file_name="sqlbuild_local.toml",
                section="settings",
                key="sql_analysis",
                value=False,
            ),
            "sqlbuild_local.toml sets [settings] sql_analysis = false",
        ),
        SettingHelpTestCase(
            "a default note says the value is the default",
            setting_note(
                file_name="sqlbuild_project.toml",
                section="references",
                key="enforce_explicit",
                value=True,
                explicit=False,
            ),
            "sqlbuild_project.toml does not set [references] enforce_explicit, "
            "so it defaults to true",
        ),
        SettingHelpTestCase(
            "a MODEL header help shows the exact entry",
            model_header_help(purpose="to skip it", entry="sql_analysis false"),
            "to skip it, add this to the MODEL header:\n            MODEL (\n"
            "              sql_analysis false,\n              ...\n            );",
        ),
        SettingHelpTestCase(
            "several helps keep one label each",
            join_helps("first", "second"),
            "first\n  = help: second",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_setting_inputs_when_rendering_help_then_shows_exact_text(
    test_case: SettingHelpTestCase,
) -> None:
    assert test_case.rendered == test_case.expected_text


@pytest.mark.parametrize(
    "test_case",
    (
        SettingSnippetTestCase(
            "microbatch concurrency",
            microbatch_guidance()[1],
            "settings",
            "microbatch_concurrency",
            True,
        ),
        SettingSnippetTestCase(
            "explicit references",
            explicit_references_help(allowed="macro-generated references"),
            "references",
            "enforce_explicit",
            False,
        ),
        SettingSnippetTestCase(
            "project-wide SQL analysis",
            sql_analysis_opt_out_help(),
            "settings",
            "sql_analysis",
            False,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_setting_guidance_when_reading_snippet_then_it_is_valid_toml_for_the_setting(
    test_case: SettingSnippetTestCase,
) -> None:
    assert parse_setting_snippet(test_case.help_text) == (
        test_case.expected_section,
        test_case.expected_key,
        test_case.expected_value,
    )


@pytest.mark.parametrize(
    "test_case",
    (
        SettingCatalogueTestCase(
            "Python and Rust diagnostics in this repository",
            Path(__file__).resolve().parents[7],
            expected_findings=(),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_error_catalogue_when_scanning_help_text_then_every_named_setting_has_toml(
    test_case: SettingCatalogueTestCase,
) -> None:
    assert tuple(find_settings_without_snippet(test_case.repository_root)) == (
        test_case.expected_findings
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
