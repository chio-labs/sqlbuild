use serde_json::Value;

use crate::review_command::main::render_review_json::render_review_json;
use crate::review_command::main::render_review_markdown::render_review_markdown;
use crate::review_command::main::render_review_text::render_review_text;
use crate::review_command::main::review_outcome::review_outcome;
use crate::review_command::tests::helpers::{
    dry_run_report, errored_report, failed_report, finding_report, incomplete_report,
    passed_report, selected_report,
};
use crate::review_command::tests::test_types::{JsonTestCase, OutcomeTestCase, RenderTestCase};

#[test]
fn given_evidence_when_deciding_outcome_then_failure_beats_findings_beats_incomplete() {
    let test_cases = [
        OutcomeTestCase {
            description: "no findings and complete coverage passes",
            report: passed_report(),
            expected_status: "passed",
            expected_exit_code: 0,
        },
        OutcomeTestCase {
            description: "a finding needs a fix",
            report: finding_report(),
            expected_status: "findings",
            expected_exit_code: 1,
        },
        OutcomeTestCase {
            description: "an incomplete check is incomplete",
            report: incomplete_report(),
            expected_status: "incomplete",
            expected_exit_code: 2,
        },
        OutcomeTestCase {
            description: "a review schema that was not dropped fails",
            report: failed_report(),
            expected_status: "failed",
            expected_exit_code: 3,
        },
        OutcomeTestCase {
            description: "an error fails even with findings",
            report: errored_report(),
            expected_status: "failed",
            expected_exit_code: 3,
        },
        OutcomeTestCase {
            description: "a dry run only plans",
            report: dry_run_report(),
            expected_status: "planned",
            expected_exit_code: 0,
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            review_outcome(&test_case.report),
            (test_case.expected_status, test_case.expected_exit_code),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_reports_when_rendering_json_then_document_is_versioned_and_complete() {
    let test_cases = [
        JsonTestCase {
            description: "a finding",
            report: finding_report(),
            expected_values: vec![
                ("/format_version", Value::from(1)),
                ("/status", Value::from("findings")),
                ("/exit_code", Value::from(1)),
                ("/summary/findings", Value::from(1)),
                ("/summary/not_validated", Value::from(1)),
                ("/findings/0/column", Value::from("amount")),
                ("/findings/0/examples/0/key", Value::from("order_id=3")),
                ("/tests/skipped", Value::from(3)),
                ("/review_schema/dropped", Value::from(true)),
                (
                    "/recall/command",
                    Value::from("sqb recall output a1b2c3d4e5f6"),
                ),
                ("/changed/1/kind", Value::from("macro")),
            ],
        },
        JsonTestCase {
            description: "a selection that added a changed ancestor and ran hooks",
            report: selected_report(),
            expected_values: vec![
                ("/added/0/name", Value::from("stg_orders")),
                ("/added/0/required_by", Value::from("order_totals")),
                ("/hooks/0", Value::from("order_totals")),
            ],
        },
        JsonTestCase {
            description: "an error",
            report: errored_report(),
            expected_values: vec![
                ("/status", Value::from("failed")),
                ("/exit_code", Value::from(3)),
                ("/error/code", Value::from("C761")),
            ],
        },
    ];
    for test_case in test_cases {
        let document: Value =
            serde_json::from_str(&render_review_json(&test_case.report)).expect("valid JSON");

        let actual: Vec<(&str, Value)> = test_case
            .expected_values
            .iter()
            .map(|(pointer, _)| {
                (
                    *pointer,
                    document.pointer(pointer).cloned().unwrap_or(Value::Null),
                )
            })
            .collect();
        assert_eq!(
            actual, test_case.expected_values,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_reports_when_rendering_markdown_then_sections_follow_the_agreed_layout() {
    let test_cases = [
        RenderTestCase {
            description: "a finding",
            report: finding_report(),
            expected_fragments: vec![
                "# Review needs a fix: 1 finding\n",
                "since `origin/main` (3f2a9c1) · head a1b2c3d · against `prod` · exit 1 · 4.50s · sqlbuild 0.172.0",
                "| Changed | Built | Compared | Tests | Findings | Not validated | Incomplete |\n|---:|---:|---:|---:|---:|---:|---:|\n| 2 | 3 | 3 | 2 | 1 | 1 | 0 |",
                "## Findings\n\n1. `order_totals.amount` values differ in 1 of 5 rows (limit: exact match)\n   - order_id=3: `12.5` → `13.0`",
                "## What changed\n\n- `stg_orders` (model): model SQL changed\n- macro `cents_to_dollars`: changed",
                "## Downstream impact\n\n```text\nstg_orders [ok]\n├── order_totals [finding]\n│   └── daily_revenue [ok, critical] columns: total_revenue\n└── order_archive [not validated: not selected (--select)]\n```",
                "## Incomplete coverage\n\nEvery check completed.",
                "## Baseline\n\n- Unchanged upstream read from `prod`: `waffle_types`\n- Incremental `order_events`: full refresh (the adapter has no zero-copy clone)",
                "## Tests and audits\n\n- Unit tests: 2 of 5 ran (3 unaffected skipped): 2 passed, 0 failed\n- Audits: 3 ran: 3 passed, 0 failed",
                "<details><summary>order_totals: 1 difference</summary>\n\n| Column | Metric | prod | branch | Limit |\n|---|---|---|---|---|\n| amount | rows differ | 0 | 1 | exact match |",
                "rows prod 5, branch 5; 2 other columns compared with no difference (full comparison).",
                "## Run details\n\n- Review schema `review_20261023t101500z_3f2a9c1_a1b2c3`: dropped\n- Downstream policy: critical (critical: `daily_revenue`)\n- Recall: `sqb recall output a1b2c3d4`",
            ],
            unexpected_fragments: vec![],
        },
        RenderTestCase {
            description: "incomplete coverage",
            report: incomplete_report(),
            expected_fragments: vec![
                "# Review incomplete: 1 check\n",
                "## Findings\n\nNo findings.",
                "## Incomplete coverage\n\n- `order_totals` keyed comparison: the model has no unique_key",
            ],
            unexpected_fragments: vec![],
        },
        RenderTestCase {
            description: "a selection that added a changed ancestor and ran hooks",
            report: selected_report(),
            expected_fragments: vec![
                "- Also built: `stg_orders`, because `order_totals` depends on it",
                "- Hooks run against the review schema: `order_totals`",
            ],
            unexpected_fragments: vec![],
        },
        RenderTestCase {
            description: "a cleanup failure",
            report: failed_report(),
            expected_fragments: vec![
                "# Review failed\n",
                "- Review schema `review_20261023t101500z_3f2a9c1_a1b2c3`: not dropped: permission denied",
            ],
            unexpected_fragments: vec![],
        },
    ];
    for test_case in test_cases {
        let markdown: String = render_review_markdown(&test_case.report);

        let present: Vec<&str> = test_case
            .expected_fragments
            .iter()
            .copied()
            .filter(|fragment| markdown.contains(fragment))
            .collect();
        let absent: Vec<&str> = test_case
            .unexpected_fragments
            .iter()
            .copied()
            .filter(|fragment| !markdown.contains(fragment))
            .collect();
        assert_eq!(
            present, test_case.expected_fragments,
            "{}: {markdown}",
            test_case.description
        );
        assert_eq!(
            absent, test_case.unexpected_fragments,
            "{}: {markdown}",
            test_case.description
        );
    }
}

#[test]
fn given_reports_when_rendering_text_then_summary_ends_with_outcome() {
    let test_cases = [RenderTestCase {
        description: "a finding",
        report: finding_report(),
        expected_fragments: vec![
            "Findings\n  1. order_totals.amount values differ in 1 of 5 rows",
            "What changed\n  stg_orders (model): model SQL changed",
            "Downstream impact\n  stg_orders [ok]\n  ├── order_totals [finding]",
            "Recall: sqb recall output a1b2c3d4",
            "\nReview needs a fix: 1 finding  changed=2  built=3  compared=3  tests=2  findings=1  not_validated=1  incomplete=0\n",
        ],
        unexpected_fragments: vec!["`"],
    }];
    for test_case in test_cases {
        let text: String = render_review_text(&test_case.report);

        let present: Vec<&str> = test_case
            .expected_fragments
            .iter()
            .copied()
            .filter(|fragment| text.contains(fragment))
            .collect();
        let absent: Vec<&str> = test_case
            .unexpected_fragments
            .iter()
            .copied()
            .filter(|fragment| !text.contains(fragment))
            .collect();
        assert_eq!(
            present, test_case.expected_fragments,
            "{}: {text}",
            test_case.description
        );
        assert_eq!(
            absent, test_case.unexpected_fragments,
            "{}: {text}",
            test_case.description
        );
    }
}
