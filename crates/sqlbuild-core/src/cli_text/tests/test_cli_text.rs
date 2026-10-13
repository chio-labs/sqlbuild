use crate::cli_text::_helpers::diagnostics::diagnostics_text;
use crate::cli_text::main::format_compile_text::format_compile_text;
use crate::cli_text::main::semantic_coverage_notice::semantic_coverage_notice;
use crate::cli_text::models::{
    CliStyle, CompileTextReport, DiagnosticText, LineageNote, ModelLine, RelatedText,
};
use crate::cli_text::tests::helpers::{diagnostic, location};
use crate::cli_text::tests::test_types::{
    CompileTextTestCase, DiagnosticsTextTestCase, NoticeTestCase,
};

/// Expectations recorded from the retired Python formatter.
#[test]
fn given_diagnostics_when_rendering_then_matches_python_text() {
    let test_cases = [DiagnosticsTextTestCase {
        description: "located error with related location and a repeated warning",
        diagnostics: vec![
            DiagnosticText {
                resource_type: Some("sql_test".to_owned()),
                resource_name: Some("orders_test".to_owned()),
                location: Some(location(2, 3, (Some(2), Some(7)))),
                related: vec![RelatedText {
                    label: "declared here".to_owned(),
                    location: location(1, 1, (Some(3), Some(1))),
                    message: Some("here".to_owned()),
                }],
                notes: vec!["n1".to_owned()],
                affected_rules: vec!["R1".to_owned(), "R2".to_owned()],
                help: Some("fix it".to_owned()),
                ..diagnostic("error", "C001", "bad column")
            },
            DiagnosticText {
                path: Some("models/b.sql".to_owned()),
                occurrences: 2,
                ..diagnostic("warning", "W001", "careful")
            },
        ],
        style: CliStyle { use_color: true },
        expected_text: "\x1b[38;5;167merror[C001]: bad column\x1b[0m\n  sql test: orders_test\n  --> models/a.sql:2:3\n    |\n  2 | FROM orders\u{e9} x\n    |   ^^^^\n\n  declared here:\n  --> models/a.sql:1:1\n    |\n  1 | SELECT 1\n    | ^^^^^^^^ here\n  \x1b[2m= note:\x1b[0m n1\n  \x1b[2m= affected Rules:\x1b[0m R1, R2\n  \x1b[2m= help:\x1b[0m fix it\n\n\x1b[33mwarning[W001]: careful\x1b[0m\n  --> models/b.sql\n  = 2 occurrences; all retained in JSON and the warning count",
    }];

    for test_case in test_cases {
        assert_eq!(
            diagnostics_text(&test_case.diagnostics, test_case.style),
            test_case.expected_text,
            "{}",
            test_case.description
        );
    }
}

/// Expectations recorded from the retired Python notice.
#[test]
fn given_partial_reasons_when_building_notice_then_groups_by_reason() {
    let test_cases = [
        NoticeTestCase {
            description: "reasons grouped across models with known and unknown actions",
            reasons: vec![
                (
                    "zeta".to_owned(),
                    vec![
                        "open source: raw_orders".to_owned(),
                        "SQL analysis disabled".to_owned(),
                    ],
                ),
                (
                    "alpha".to_owned(),
                    vec!["open source: raw_orders".to_owned(), "weird".to_owned()],
                ),
            ],
            expected_notice: Some(
                "Semantic checks were partial for 2 models:\n  zeta: SQL analysis disabled; enable sql_analysis, then run `sqb compile --no-cache`.\n  alpha, zeta: reads open source raw_orders; run `sqb contract generate --from <target> --select source:raw_orders --write` and enforce the complete source contract.\n  alpha: weird; declare the input shape, then run `sqb compile --no-cache`.",
            ),
        },
        NoticeTestCase {
            description: "complete checks print no notice",
            reasons: Vec::new(),
            expected_notice: None,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            semantic_coverage_notice(&test_case.reasons).as_deref(),
            test_case.expected_notice,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_report_when_formatting_then_lists_models_and_summary() {
    let test_cases = [CompileTextTestCase {
        description: "one plain model with a manifest and unavailable lineage",
        report: CompileTextReport {
            style: CliStyle { use_color: false },
            models: vec![ModelLine {
                name: "orders".to_owned(),
                failed: false,
                column_count: 2,
            }],
            semantic_notice: None,
            diagnostics: Vec::new(),
            seed_count: 1,
            function_count: 0,
            error_count: 0,
            warning_count: 0,
            compiled_dir: "target/compiled".to_owned(),
            manifest: true,
            lineage: LineageNote::Unavailable,
        },
        expected_text: "\nCompile ready  1 model\n\n\u{2514}\u{2500}\u{2500} orders                   OK   2 columns\n\n\u{2713} Project compiled  1 model, 1 seed, 0 functions, 0 errors, 0 warnings\n  Wrote: target/compiled/\n  Wrote: target/manifest.json\n  Column lineage: unavailable\n",
    }];

    for test_case in test_cases {
        assert_eq!(
            format_compile_text(&test_case.report),
            test_case.expected_text,
            "{}",
            test_case.description
        );
    }
}
