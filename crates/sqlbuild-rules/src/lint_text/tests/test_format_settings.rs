use std::fs;

use tempfile::TempDir;

use crate::lint_text::main::resolve_format_settings::resolve_format_settings;
use crate::lint_text::models::FormatSettings;
use crate::lint_text::tests::test_types::FormatSettingsTestCase;

#[test]
fn given_project_config_when_resolving_format_settings_then_values_match_python() {
    let test_cases = [
        FormatSettingsTestCase {
            description: "format widths, thresholds and a translated local adapter",
            project_toml: "\u{feff}name = \"demo\"\nadapter = \"duckdb\"\n[format]\nline_width = 80\nmax_description_lines = 0\n[rules.thresholds]\nmax_literal_length = 40\nmax_ranking_order_by = true\n",
            local_toml: "adapter = \"sqlserver\"\n",
            expected_settings: FormatSettings {
                line_width: 80,
                max_description_lines: 10,
                dialect: "tsql".to_owned(),
                max_literal_length: 40,
                max_ranking_order_by: 5,
                has_project_config: true,
            },
        },
        FormatSettingsTestCase {
            description: "an unknown adapter names its own dialect",
            project_toml: "name = \"demo\"\nadapter = \"warehouse\"\n",
            local_toml: "",
            expected_settings: FormatSettings {
                line_width: 100,
                max_description_lines: 10,
                dialect: "warehouse".to_owned(),
                max_literal_length: 100,
                max_ranking_order_by: 5,
                has_project_config: true,
            },
        },
    ];

    for test_case in test_cases {
        let project: TempDir = TempDir::new().expect("temporary project");
        fs::write(
            project.path().join("sqlbuild_project.toml"),
            test_case.project_toml,
        )
        .expect("project config");
        fs::write(
            project.path().join("sqlbuild_local.toml"),
            test_case.local_toml,
        )
        .expect("local config");
        assert_eq!(
            resolve_format_settings(project.path()),
            Ok(test_case.expected_settings),
            "{}",
            test_case.description
        );
    }
}
