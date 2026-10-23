use crate::cli_text::models::CliStyle;
use crate::janitor_text::main::format_janitor_json::format_janitor_json;
use crate::janitor_text::main::janitor_confirmation_phrase::janitor_confirmation_phrase;
use crate::janitor_text::main::janitor_confirmation_prompt::janitor_confirmation_prompt;
use crate::janitor_text::main::render_janitor_plan::render_janitor_plan;
use crate::janitor_text::models::JanitorOutcome;
use crate::janitor_text::tests::helpers::{direct_archive_plan, unchecked_plan, usage_plan};
use crate::janitor_text::tests::test_types::{JsonTestCase, PreviewTestCase};

const PLAIN: CliStyle = CliStyle { use_color: false };

#[test]
fn given_usage_check_when_rendering_preview_then_in_use_relations_show_readers() {
    let test_cases = [
        PreviewTestCase {
            description: "in-use candidates are listed with capped readers and archived anyway",
            plan: usage_plan(false),
            verbose: false,
            expected_fragments: &[
                "  relations to archive   3\n  in use                 2\n",
                "\nIn use\n  dev.orders_daily  queried 2026-10-21 by svc_reporting \
                 (14 queries in 7 days)\n",
                "  dev.old_orders  queried 2026-10-21 by svc_reporting, alice, bob +2 more \
                 (40 queries in 7 days); frozen since 2026-09-01, still in use\n",
                "  dev.old_customers  ->  dev._sqb_archive__",
            ],
            unexpected_fragments: &[
                "Kept (in use)",
                "dev.old_customers  queried",
                "dev.orders_daily  queried 2026-10-21 by svc_reporting (14 queries in 7 days); frozen",
                "usage not checked",
            ],
        },
        PreviewTestCase {
            description: "keep_in_use lists in-use relations as kept and leaves them unarchived",
            plan: usage_plan(true),
            verbose: false,
            expected_fragments: &[
                "  relations to archive   1\n  kept (in use)          2\n",
                "\nKept (in use)\n  dev.orders_daily  queried 2026-10-21",
                "  dev.old_orders  queried 2026-10-21 by svc_reporting, alice, bob +2 more",
            ],
            unexpected_fragments: &["\nIn use\n", "dev.old_orders  ->", "dev.orders_daily  ->"],
        },
        PreviewTestCase {
            description: "an unchecked usage shows one notice and no in-use rows",
            plan: unchecked_plan(false),
            verbose: false,
            expected_fragments: &["\n  usage not checked: unsupported adapter\n"],
            unexpected_fragments: &["in use  ", "In use", "nothing kept in use"],
        },
        PreviewTestCase {
            description: "keep_in_use without a usage source warns that nothing is kept",
            plan: unchecked_plan(true),
            verbose: false,
            expected_fragments: &[
                "  usage not checked: unsupported adapter\n  nothing kept in use: no usage \
                 could be checked, so relations in use are archived too\n",
            ],
            unexpected_fragments: &["Kept (in use)"],
        },
        PreviewTestCase {
            description: "a plan without a usage check renders as before",
            plan: direct_archive_plan(),
            verbose: false,
            expected_fragments: &["  relations to archive   1\n  archives to delete"],
            unexpected_fragments: &["usage", "in use"],
        },
    ];

    for test_case in test_cases {
        let text: String = render_janitor_plan(&test_case.plan, test_case.verbose, PLAIN);
        for fragment in test_case.expected_fragments {
            assert!(
                text.contains(fragment),
                "{}: missing {fragment:?} in {text}",
                test_case.description
            );
        }
        for fragment in test_case.unexpected_fragments {
            assert!(
                !text.contains(fragment),
                "{}: unexpected {fragment:?} in {text}",
                test_case.description
            );
        }
    }
}

#[test]
fn given_usage_check_when_prompting_then_prompt_states_in_use_count() {
    let test_cases: [(&str, crate::janitor_text::models::JanitorPlanText, &str); 4] = [
        (
            "the prompt counts in-use relations among those archived",
            usage_plan(false),
            "Janitor will archive 3 and delete 0 objects from dev.\n\
             3 relations will be archived; 2 of them are in use.\nRetention: 14 days\n",
        ),
        (
            "keep_in_use counts the kept relations",
            usage_plan(true),
            "Janitor will archive 1 and delete 0 objects from dev.\n\
             2 relations in use are kept.\nRetention: 14 days\n",
        ),
        (
            "an unchecked usage repeats the notice",
            unchecked_plan(false),
            "Janitor will archive 1 and delete 1 objects from dev.\n\
             Usage not checked: unsupported adapter\nRetention: 14 days\n",
        ),
        (
            "keep_in_use without a usage source repeats the warning",
            unchecked_plan(true),
            "Usage not checked: unsupported adapter\nNothing kept in use: no usage could be \
             checked, so relations in use are archived too\nRetention",
        ),
    ];

    for (description, plan, expected) in test_cases {
        let prompt: String = janitor_confirmation_prompt(&plan);
        assert!(
            prompt.contains(expected),
            "{description}: missing {expected:?} in {prompt}"
        );
    }
    assert_eq!(
        janitor_confirmation_phrase(&usage_plan(true)),
        "archive 1 and delete 0 objects from dev"
    );
}

#[test]
fn given_usage_check_when_formatting_json_then_candidates_carry_in_use() {
    let test_cases = [
        JsonTestCase {
            description: "checked candidates carry their reads or false, with the check status",
            plan: Some(usage_plan(false)),
            outcome: JanitorOutcome::Previewed,
            run: None,
            error: None,
            expected_fragments: &[
                "\"in_use\": {\n          \"last_read\": \"2026-10-21T09:30:00Z\",\n          \
                 \"readers\": [\n            \"svc_reporting\"\n          ],\n          \
                 \"query_count\": 14\n        }",
                "\"in_use\": false",
                "\"kept_in_use\": []",
                "\"usage_check\": {\n    \"status\": \"checked\",\n    \"reason\": null,\n    \
                 \"window\": \"7d\",\n    \"keep_in_use\": false\n  }",
            ],
        },
        JsonTestCase {
            description: "kept relations are listed apart from the relations to archive",
            plan: Some(usage_plan(true)),
            outcome: JanitorOutcome::Previewed,
            run: None,
            error: None,
            expected_fragments: &[
                "\"kept_in_use\": [\n      {\n        \"name\": \"dev.orders_daily\"",
                "\"keep_in_use\": true",
            ],
        },
        JsonTestCase {
            description: "an unchecked usage leaves in_use null and states the reason",
            plan: Some(unchecked_plan(false)),
            outcome: JanitorOutcome::Previewed,
            run: None,
            error: None,
            expected_fragments: &[
                "\"in_use\": null",
                "\"status\": \"not_checked\",\n    \"reason\": \"unsupported adapter\"",
            ],
        },
        JsonTestCase {
            description: "no usage check is null",
            plan: Some(direct_archive_plan()),
            outcome: JanitorOutcome::Previewed,
            run: None,
            error: None,
            expected_fragments: &["\"usage_check\": null", "\"in_use\": null"],
        },
    ];

    for test_case in test_cases {
        let text: String = format_janitor_json(
            test_case.plan.as_ref(),
            test_case.outcome,
            test_case.run.as_ref(),
            test_case.error,
        );
        for fragment in test_case.expected_fragments {
            assert!(
                text.contains(fragment),
                "{}: missing {fragment:?} in {text}",
                test_case.description
            );
        }
    }
}
