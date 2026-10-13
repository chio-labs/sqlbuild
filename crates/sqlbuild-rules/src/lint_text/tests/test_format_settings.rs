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

#[test]
fn given_relative_paths_when_classifying_headers_then_only_plain_models_scan_one_header() {
    let test_cases = [
        crate::lint_text::tests::test_types::FirstHeaderTestCase {
            description: "a plain model file",
            relative_parts: &["models", "staging", "orders.sql"],
            expected_first_only: true,
        },
        crate::lint_text::tests::test_types::FirstHeaderTestCase {
            description: "a scoped declaration file under models",
            relative_parts: &["models", "_enums", "status.sql"],
            expected_first_only: false,
        },
        crate::lint_text::tests::test_types::FirstHeaderTestCase {
            description: "a declaration group file under models",
            relative_parts: &["models", "_sqlbuild", "orders.sql"],
            expected_first_only: false,
        },
        crate::lint_text::tests::test_types::FirstHeaderTestCase {
            description: "a file named like a folder is still a model",
            relative_parts: &["models", "enums.sql"],
            expected_first_only: true,
        },
        crate::lint_text::tests::test_types::FirstHeaderTestCase {
            description: "files outside models scan every header",
            relative_parts: &["tests", "unit", "orders.sql"],
            expected_first_only: false,
        },
    ];

    for test_case in test_cases {
        let parts: Vec<String> = test_case
            .relative_parts
            .iter()
            .map(|part| (*part).to_owned())
            .collect();
        assert_eq!(
            crate::lint_text::main::first_header_only::first_header_only(&parts),
            test_case.expected_first_only,
            "{}",
            test_case.description
        );
    }
}
