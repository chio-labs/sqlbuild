use crate::cli_text::models::CliStyle;
use crate::janitor_text::main::format_janitor_json::format_janitor_json;
use crate::janitor_text::main::janitor_item_counts::janitor_item_counts;
use crate::janitor_text::main::janitor_nothing_to_do_text::janitor_nothing_to_do_text;
use crate::janitor_text::main::janitor_phase_complete_text::janitor_phase_complete_text;
use crate::janitor_text::main::janitor_phase_failed_text::janitor_phase_failed_text;
use crate::janitor_text::main::janitor_phase_flow_width::janitor_phase_flow_width;
use crate::janitor_text::main::janitor_phase_start_text::janitor_phase_start_text;
use crate::janitor_text::main::render_janitor_completion::render_janitor_completion;
use crate::janitor_text::main::render_janitor_item_line::render_janitor_item_line;
use crate::janitor_text::main::render_janitor_plan::render_janitor_plan;
use crate::janitor_text::models::{
    JanitorOutcome, JanitorPhase, JanitorResultCounts, JanitorRunText,
};
use crate::janitor_text::tests::helpers::{direct_archive_plan, item, large_plan};
use crate::janitor_text::tests::test_types::{
    CompletionTestCase, ItemLineTestCase, JsonTestCase, PhaseTextTestCase, PreviewTestCase,
};

const PLAIN: CliStyle = CliStyle { use_color: false };

#[test]
fn given_finished_action_when_rendering_then_line_aligns_position_flow_and_status() {
    let test_cases = [
        ItemLineTestCase {
            description: "a rename pads its flow to the phase width",
            position: (1, 12),
            item: item(
                JanitorPhase::Archive,
                ("archived", "dev.orders", Some("dev._a")),
                None,
            ),
            flow_width: 24,
            expected_line: "   1/12  archived  dev.orders -> dev._a      OK  0.50s",
        },
        ItemLineTestCase {
            description: "a failure shows the first line of its error",
            position: (3, 3),
            item: item(
                JanitorPhase::DeleteArchives,
                ("deleted", "dev.old", None),
                Some("permission denied\nquery id 1"),
            ),
            flow_width: 0,
            expected_line: "  3/3  deleted   dev.old  FAIL  0.50s  permission denied",
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            render_janitor_item_line(
                test_case.position,
                &test_case.item,
                test_case.flow_width,
                PLAIN
            ),
            test_case.expected_line,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_phase_when_rendering_progress_then_start_complete_and_failure_count_its_actions() {
    let test_cases = [
        PhaseTextTestCase {
            description: "one archive uses singular nouns and seconds",
            phase: JanitorPhase::Archive,
            items: vec![item(
                JanitorPhase::Archive,
                ("archived", "dev.a", Some("dev.b")),
                None,
            )],
            total: 1,
            elapsed_seconds: 0.25,
            expected_start: "Archiving 1 relation...",
            expected_complete: "Archived 1 relation. (0.25s)",
            expected_failed: "\u{2717} Archiving failed  after 1 of 1 relation  (0.25s)",
        },
        PhaseTextTestCase {
            description: "old-name views count drops apart from views already gone",
            phase: JanitorPhase::DropOldNameViews,
            items: vec![
                item(
                    JanitorPhase::DropOldNameViews,
                    ("dropped", "dev.a", None),
                    None,
                ),
                item(
                    JanitorPhase::DropOldNameViews,
                    ("recorded", "dev.b", None),
                    None,
                ),
                item(
                    JanitorPhase::DropOldNameViews,
                    ("dropped", "dev.c", None),
                    Some("denied"),
                ),
            ],
            total: 3,
            elapsed_seconds: 75.4,
            expected_start: "Dropping 3 old-name views...",
            expected_complete: "Dropped 1 old-name view and recorded 1 already gone. (1m 15s)",
            expected_failed: "\u{2717} Dropping failed  after 2 of 3 old-name views  (1m 15s)",
        },
        PhaseTextTestCase {
            description: "hour-long phases show hours, minutes and seconds",
            phase: JanitorPhase::PruneDirectState,
            items: Vec::new(),
            total: 2,
            elapsed_seconds: 3725.0,
            expected_start: "Pruning 2 direct state tables...",
            expected_complete: "Pruned 0 direct state tables. (1h 02m 05s)",
            expected_failed: "\u{2717} Pruning failed  after 0 of 2 direct state tables  (1h 02m 05s)",
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            janitor_phase_start_text(test_case.phase, test_case.total),
            test_case.expected_start,
            "{}",
            test_case.description
        );
        assert_eq!(
            janitor_phase_complete_text(
                test_case.phase,
                &test_case.items,
                test_case.elapsed_seconds
            ),
            test_case.expected_complete,
            "{}",
            test_case.description
        );
        let completed: usize = test_case
            .items
            .iter()
            .filter(|item| item.error.is_none())
            .count();
        assert_eq!(
            janitor_phase_failed_text(
                test_case.phase,
                (completed, test_case.total),
                test_case.elapsed_seconds,
                PLAIN
            ),
            test_case.expected_failed,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_run_counts_when_rendering_completion_then_final_line_is_unambiguous() {
    let test_cases = [
        CompletionTestCase {
            description: "a completed run totals archives, deletions and prunes",
            counts: JanitorResultCounts {
                archived: 608,
                deleted_archives: 6,
                pruned_direct_state: 6,
                ..JanitorResultCounts::default()
            },
            elapsed_seconds: Some(302.0),
            failed: false,
            expected_text: "\u{2713} Janitor completed  archived 608, deleted 6, pruned 6  (5m 02s)\n",
        },
        CompletionTestCase {
            description: "a failed run reports what finished before the failure",
            counts: JanitorResultCounts {
                archived: 11,
                ..JanitorResultCounts::default()
            },
            elapsed_seconds: Some(65.0),
            failed: true,
            expected_text: "\u{2717} Janitor failed  archived 11, deleted 0, pruned 0  (1m 05s)\n",
        },
    ];

    for test_case in test_cases {
        assert_eq!(
            render_janitor_completion(
                &test_case.counts,
                test_case.elapsed_seconds,
                test_case.failed,
                PLAIN
            ),
            test_case.expected_text,
            "{}",
            test_case.description
        );
    }
    assert_eq!(
        janitor_nothing_to_do_text(PLAIN),
        "\u{2713} Janitor completed  nothing to clean up\n"
    );
}

#[test]
fn given_finished_actions_when_counting_then_only_successes_count_by_kind() {
    let items = vec![
        item(JanitorPhase::Archive, ("archived", "a", Some("b")), None),
        item(
            JanitorPhase::Archive,
            ("archived", "c", Some("d")),
            Some("denied"),
        ),
        item(JanitorPhase::DeleteArchives, ("deleted", "e", None), None),
        item(JanitorPhase::DropOldNameViews, ("dropped", "f", None), None),
        item(
            JanitorPhase::DropOldNameViews,
            ("recorded", "g", None),
            None,
        ),
        item(
            JanitorPhase::DropQueryArtifacts,
            ("dropped", "h", None),
            None,
        ),
        item(JanitorPhase::PruneDirectState, ("pruned", "i", None), None),
    ];

    assert_eq!(
        janitor_item_counts(&items),
        JanitorResultCounts {
            archived: 1,
            deleted: 0,
            deleted_archives: 1,
            deleted_query_artifacts: 1,
            dropped_old_name_views: 1,
            pruned_direct_state: 1,
        }
    );
    assert_eq!(
        janitor_phase_flow_width(&large_plan(3, 0), JanitorPhase::Archive),
        72
    );
}

#[test]
fn given_long_plan_when_previewing_then_lists_are_capped_unless_verbose() {
    let test_cases = [
        PreviewTestCase {
            description: "long lists show ten entries and skipped objects group by reason",
            plan: large_plan(25, 7),
            verbose: false,
            expected_fragments: &[
                "  dev.old_orders_009  ->  ",
                "  ... and 15 more (use --verbose to show all)\n",
                "Skipped objects (7)\n  4  not tracked by SQLBuild\n  3  relation is newer than 14 days\n",
                "  relations to archive   25\n",
            ],
            unexpected_fragments: &["dev.old_orders_010  ->", "dev.recent_000"],
        },
        PreviewTestCase {
            description: "verbose lists every entry and every skipped object",
            plan: large_plan(25, 7),
            verbose: true,
            expected_fragments: &[
                "  dev.old_orders_024  ->  ",
                "Skipped objects\n  dev.recent_000  relation is newer than 14 days\n",
            ],
            unexpected_fragments: &["... and", "Skipped objects (7)"],
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
                "{}: unexpected {fragment:?}",
                test_case.description
            );
        }
    }
}

#[test]
fn given_outcome_when_formatting_json_then_document_carries_plan_result_and_error() {
    let run: JanitorRunText = JanitorRunText {
        items: vec![item(
            JanitorPhase::Archive,
            ("archived", "dev.old_orders", Some("dev._a")),
            None,
        )],
        counts: JanitorResultCounts {
            archived: 1,
            ..JanitorResultCounts::default()
        },
        elapsed_seconds: 1.5,
    };
    let test_cases = [
        JsonTestCase {
            description: "a completed run lists its actions",
            outcome: JanitorOutcome::Completed,
            run: Some(run.clone()),
            error: None,
            expected_fragments: &[
                "\"target\": \"dev\"",
                "\"status\": \"completed\"",
                "\"relations_to_archive\": [",
                "\"name\": \"dev.old_orders\"",
                "\"phase\": \"archive\"",
                "\"status\": \"ok\"",
                "\"archived\": 1",
                "\"error\": null",
            ],
        },
        JsonTestCase {
            description: "a failed run carries its error",
            outcome: JanitorOutcome::Failed,
            run: Some(run),
            error: Some("rename denied"),
            expected_fragments: &["\"status\": \"failed\"", "\"error\": \"rename denied\""],
        },
        JsonTestCase {
            description: "a preview has no result",
            outcome: JanitorOutcome::Previewed,
            run: None,
            error: None,
            expected_fragments: &["\"status\": \"previewed\"", "\"result\": null"],
        },
    ];

    for test_case in test_cases {
        let text: String = format_janitor_json(
            Some(&direct_archive_plan()),
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
    assert!(
        format_janitor_json(None, JanitorOutcome::Disabled, None, None).contains("\"plan\": null")
    );
}
