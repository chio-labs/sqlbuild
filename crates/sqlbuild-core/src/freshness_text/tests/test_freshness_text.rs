use crate::cli_text::models::CliStyle;
use crate::freshness_text::main::freshness_exit_code::freshness_exit_code;
use crate::freshness_text::main::freshness_json::freshness_json;
use crate::freshness_text::main::freshness_status::freshness_status;
use crate::freshness_text::main::render_freshness_text::render_freshness_text;
use crate::freshness_text::models::{FreshnessSourceResult, FreshnessStatus, StateComparison};
use crate::freshness_text::tests::helpers::{mixed_results, observed, results_with};
use crate::freshness_text::tests::test_types::{
    ExitCodeTestCase, JsonTestCase, StatusTestCase, TextTestCase,
};

#[test]
fn given_results_when_rendering_text_then_groups_sources_by_status() {
    let test_cases = [
        TextTestCase {
            description: "observed, unknown and error groups with an age footer",
            results: mixed_results(),
            use_color: false,
            expected_fragments: &[
                "Source freshness\n\nObserved (4)\n",
                "\u{251c}\u{2500}\u{2500} raw_orders     value 2026-01-01T00:00:00  kind timestamp  via sql  tolerance 15m  age warn\n",
                "\u{2514}\u{2500}\u{2500} raw_inventory  value 42  kind timestamp  via sql  age unknown\n",
                "\nUnknown (1)\n\u{2514}\u{2500}\u{2500} raw_payments   no freshness config and adapter metadata unavailable\n",
                "\nErrors (1)\n\u{2514}\u{2500}\u{2500} raw_events     freshness query failed\n",
                "\nOBSERVED=4  CHANGED=0  UNCHANGED=0  TOLERATED=0  UNKNOWN=1  ERROR=1\n",
                "Age policy  PASS=1  WARN=1  ERROR=1  UNKNOWN=1\n",
            ],
        },
        TextTestCase {
            description: "colored output styles ages and messages by status",
            results: mixed_results(),
            use_color: true,
            expected_fragments: &[
                "\u{1b}[34m\u{1b}[1mSource freshness\u{1b}[0m",
                "\u{1b}[33mage warn\u{1b}[0m",
                "\u{1b}[32mage pass\u{1b}[0m",
                "\u{1b}[38;5;167mage error\u{1b}[0m",
                "\u{1b}[33mno freshness config and adapter metadata unavailable\u{1b}[0m",
                "\u{1b}[38;5;167mfreshness query failed\u{1b}[0m",
                "\u{1b}[2mUNKNOWN=\u{1b}[0m\u{1b}[33m1\u{1b}[0m",
            ],
        },
        TextTestCase {
            description: "compared sources show previous and current versions",
            results: vec![FreshnessSourceResult {
                status: FreshnessStatus::Changed,
                previous_data_version: Some("1".to_owned()),
                ..observed("raw_orders", "2", None)
            }],
            use_color: false,
            expected_fragments: &[
                "Changed (1)\n\u{2514}\u{2500}\u{2500} raw_orders  previous 1  current 2\n\n",
                "OBSERVED=0  CHANGED=1",
            ],
        },
        TextTestCase {
            description: "no sources render only the title and footer",
            results: Vec::new(),
            use_color: false,
            expected_fragments: &[
                "Source freshness\n\nOBSERVED=0  CHANGED=0  UNCHANGED=0  TOLERATED=0  UNKNOWN=0  ERROR=0\n",
            ],
        },
    ];

    for test_case in test_cases {
        let text: String = render_freshness_text(
            &test_case.results,
            CliStyle {
                use_color: test_case.use_color,
            },
        );
        assert!(
            test_case
                .expected_fragments
                .iter()
                .all(|fragment| text.contains(fragment)),
            "{}: {text}",
            test_case.description
        );
    }
}

#[test]
fn given_results_when_serializing_then_matches_indented_json() {
    let test_cases = [JsonTestCase {
        description: "one observed source with all fields and the summary",
        results: vec![observed("raw_orders", "1", Some("pass"))],
        expected_json: "{\n  \"sources\": [\n    {\n      \"name\": \"raw_orders\",\n      \
            \"status\": \"observed\",\n      \"strategy\": \"sql\",\n      \
            \"value_kind\": \"timestamp\",\n      \"current_data_version\": \"1\",\n      \
            \"previous_data_version\": null,\n      \"lag_tolerance\": null,\n      \
            \"target\": {\n        \"database\": null,\n        \"schema\": null,\n        \
            \"name\": null\n      },\n      \"message\": null,\n      \"age_status\": \"pass\"\n    \
            }\n  ],\n  \"summary\": {\n    \"observed\": 1,\n    \"changed\": 0,\n    \
            \"unchanged\": 0,\n    \"tolerated\": 0,\n    \"unknown\": 0,\n    \"errors\": 0,\n    \
            \"age_pass\": 1,\n    \"age_warn\": 0,\n    \"age_error\": 0,\n    \"age_unknown\": 0\n  }\n}",
    }];

    for test_case in test_cases {
        assert_eq!(
            freshness_json(&test_case.results).ok().as_deref(),
            Some(test_case.expected_json),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_statuses_when_computing_exit_code_then_honours_fail_flags() {
    let test_cases = [
        ExitCodeTestCase {
            description: "no flags always succeed",
            statuses: &[FreshnessStatus::Error],
            flags: (false, false),
            expected_code: 0,
        },
        ExitCodeTestCase {
            description: "fail on stale fails for changed sources",
            statuses: &[FreshnessStatus::Changed],
            flags: (true, false),
            expected_code: 1,
        },
        ExitCodeTestCase {
            description: "fail on error ignores changed sources",
            statuses: &[FreshnessStatus::Changed, FreshnessStatus::Tolerated],
            flags: (false, true),
            expected_code: 0,
        },
        ExitCodeTestCase {
            description: "fail on error fails for unknown sources",
            statuses: &[FreshnessStatus::Unknown],
            flags: (false, true),
            expected_code: 1,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            freshness_exit_code(&results_with(test_case.statuses), test_case.flags),
            test_case.expected_code,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_state_comparison_when_classifying_then_returns_status() {
    let test_cases = [
        StatusTestCase {
            description: "no state comparison observes",
            comparison: StateComparison::NotCompared,
            expected_status: FreshnessStatus::Observed,
        },
        StatusTestCase {
            description: "missing previous state is unknown",
            comparison: StateComparison::Missing,
            expected_status: FreshnessStatus::Unknown,
        },
        StatusTestCase {
            description: "equal hashes are unchanged",
            comparison: StateComparison::Equivalent { same_hash: true },
            expected_status: FreshnessStatus::Unchanged,
        },
        StatusTestCase {
            description: "equivalent within tolerance is tolerated",
            comparison: StateComparison::Equivalent { same_hash: false },
            expected_status: FreshnessStatus::Tolerated,
        },
        StatusTestCase {
            description: "different records changed",
            comparison: StateComparison::Different,
            expected_status: FreshnessStatus::Changed,
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            freshness_status(test_case.comparison),
            test_case.expected_status,
            "{}",
            test_case.description
        );
    }
}
