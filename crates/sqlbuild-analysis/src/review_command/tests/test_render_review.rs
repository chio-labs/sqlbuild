use serde_json::Value;

use crate::review_command::main::render_review_json::render_review_json;
use crate::review_command::main::render_review_markdown::render_review_markdown;
use crate::review_command::main::render_review_text::render_review_text;
use crate::review_command::main::review_outcome::review_outcome;
use crate::review_command::models::{ReviewError, ReviewReport};
use crate::review_command::tests::helpers::{finding_report, incomplete_report};
use crate::review_command::tests::test_types::{OutcomeTestCase, RenderTestCase};

fn failed_report() -> ReviewReport {
    let mut report: ReviewReport = incomplete_report();
    if let Some(schema) = report.schema.as_mut() {
        schema.dropped = false;
        schema.error = Some("permission denied".to_owned());
    }
    report
}

fn passed_report() -> ReviewReport {
    let mut report: ReviewReport = incomplete_report();
    report.incomplete.clear();
    report
}

#[test]
fn given_evidence_when_deciding_outcome_then_failure_beats_findings_beats_incomplete() {
    let mut errored: ReviewReport = finding_report();
    errored.error = Some(ReviewError {
        code: "C761".to_owned(),
        message: "--select x matches no model or seed".to_owned(),
        help: None,
    });
    let mut dry_run: ReviewReport = passed_report();
    dry_run.dry_run = true;
    let test_cases = [
        OutcomeTestCase {
            description: "no findings and complete coverage passes",
            report: passed_report(),
            expected: ("passed", 0),
        },
        OutcomeTestCase {
            description: "a finding needs a fix",
            report: finding_report(),
            expected: ("findings", 1),
        },
        OutcomeTestCase {
            description: "an incomplete check is incomplete",
            report: incomplete_report(),
            expected: ("incomplete", 2),
        },
        OutcomeTestCase {
            description: "a review schema that was not dropped fails",
            report: failed_report(),
            expected: ("failed", 3),
        },
        OutcomeTestCase {
            description: "an error fails even with findings",
            report: errored,
            expected: ("failed", 3),
        },
        OutcomeTestCase {
            description: "a dry run only plans",
            report: dry_run,
            expected: ("planned", 0),
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            review_outcome(&test_case.report),
            test_case.expected,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_finding_report_when_rendering_json_then_document_is_versioned_and_complete() {
    let document: Value =
        serde_json::from_str(&render_review_json(&finding_report())).expect("valid JSON");

    assert_eq!(document["format_version"], 1);
    assert_eq!(document["status"], "findings");
    assert_eq!(document["exit_code"], 1);
    assert_eq!(document["summary"]["findings"], 1);
    assert_eq!(document["summary"]["not_validated"], 1);
    assert_eq!(document["findings"][0]["column"], "amount");
    assert_eq!(document["findings"][0]["examples"][0]["key"], "order_id=3");
    assert_eq!(document["tests"]["skipped"], 3);
    assert_eq!(document["review_schema"]["dropped"], true);
    assert_eq!(
        document["recall"]["command"],
        "sqb recall output a1b2c3d4e5f6"
    );
    assert_eq!(document["changed"][1]["kind"], "macro");
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
                "## Run details\n\n- Review schema `REVIEW_20261023T101500Z_3f2a9c1_a1b2c3`: dropped\n- Downstream policy: critical (critical: `daily_revenue`)\n- Recall: `sqb recall output a1b2c3d4e5f6`",
            ],
        },
        RenderTestCase {
            description: "incomplete coverage",
            report: incomplete_report(),
            expected_fragments: vec![
                "# Review incomplete: 1 check\n",
                "## Findings\n\nNo findings.",
                "## Incomplete coverage\n\n- `order_totals` keyed comparison: the model has no unique_key",
            ],
        },
        RenderTestCase {
            description: "a cleanup failure",
            report: failed_report(),
            expected_fragments: vec![
                "# Review failed\n",
                "- Review schema `REVIEW_20261023T101500Z_3f2a9c1_a1b2c3`: not dropped: permission denied",
            ],
        },
    ];
    for test_case in test_cases {
        let markdown: String = render_review_markdown(&test_case.report);

        for fragment in &test_case.expected_fragments {
            assert!(
                markdown.contains(fragment),
                "{}: missing {fragment:?} in\n{markdown}",
                test_case.description
            );
        }
    }
}

#[test]
fn given_finding_report_when_rendering_text_then_summary_ends_with_outcome() {
    let text: String = render_review_text(&finding_report());

    assert!(text.contains("Findings\n  1. order_totals.amount values differ in 1 of 5 rows"));
    assert!(text.contains("Downstream impact\n  stg_orders [ok]\n  ├── order_totals [finding]"));
    assert!(text.contains("Recall: sqb recall output a1b2c3d4e5f6"));
    assert!(text.contains(
        "\nReview needs a fix: 1 finding  changed=2  built=3  compared=3  tests=2  findings=1  not_validated=1  incomplete=0\n"
    ));
    assert!(!text.contains('`'));
}
