use crate::microbatches::main::project_coverage::project_coverage;
use crate::microbatches::main::project_replay::project_replay;
use crate::microbatches::models::{CoveragePiece, ReplayState, ReplayVersions};
use crate::microbatches::tests::helpers::{completion, interval, owned, texts};
use crate::microbatches::tests::test_types::{CoverageTestCase, ReplayTestCase};

#[test]
fn given_completion_history_when_projecting_then_latest_completion_and_gaps_are_derived() {
    let test_cases = [
        CoverageTestCase {
            description: "newer overlapping completion wins and a middle gap is known missing",
            completions: vec![
                completion("a", (0, 2), 1.0),
                completion("b", (1, 2), 2.0),
                completion("c", (3, 4), 3.0),
            ],
            expected: vec![
                interval(0, 1),
                interval(1, 2),
                interval(2, 3),
                interval(3, 4),
            ],
            expected_segments: vec![("0", "1", 0), ("1", "2", 1), ("3", "4", 2)],
            expected_frontier: Some("2"),
            expected_known_missing: vec![("2", "3")],
            expected_unaccounted: Vec::new(),
        },
        CoverageTestCase {
            description: "no history leaves every expected interval unaccounted",
            completions: Vec::new(),
            expected: vec![interval(5, 6)],
            expected_segments: Vec::new(),
            expected_frontier: Some("5"),
            expected_known_missing: Vec::new(),
            expected_unaccounted: vec![("5", "6")],
        },
    ];

    for test_case in test_cases {
        let projection = project_coverage(&test_case.completions, &test_case.expected);
        let segments: Vec<(String, String, usize)> = projection
            .segments
            .iter()
            .map(|segment| {
                (
                    segment.interval.start.clone(),
                    segment.interval.end.clone(),
                    segment.completion,
                )
            })
            .collect();
        let expected_segments: Vec<(String, String, usize)> = test_case
            .expected_segments
            .iter()
            .map(|(start, end, index)| ((*start).to_owned(), (*end).to_owned(), *index))
            .collect();
        assert_eq!(segments, expected_segments, "{}", test_case.description);
        assert_eq!(
            projection.contiguous_frontier.as_deref(),
            test_case.expected_frontier,
            "{}",
            test_case.description
        );
        assert_eq!(
            texts(&projection.known_missing),
            owned(&test_case.expected_known_missing),
            "{}",
            test_case.description
        );
        assert_eq!(
            texts(&projection.unaccounted),
            owned(&test_case.expected_unaccounted),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_replay_requirement_when_projecting_then_state_follows_coverage_versions() {
    let piece = |start: i128, end: i128, version: &str, unknown: bool| CoveragePiece {
        interval: interval(start, end),
        unknown_fingerprint: unknown,
        model_version_hash: Some(version.to_owned()),
    };
    let test_cases = [
        ReplayTestCase {
            description: "other version is superseded",
            required: Some("F1"),
            coverage: Vec::new(),
            expected_state: ReplayState::Superseded,
            expected_missing: Vec::new(),
        },
        ReplayTestCase {
            description: "current version everywhere is verified",
            required: Some("F2"),
            coverage: vec![piece(0, 2, "F2", false)],
            expected_state: ReplayState::VerifiedComplete,
            expected_missing: Vec::new(),
        },
        ReplayTestCase {
            description: "old version piece is missing",
            required: Some("F2"),
            coverage: vec![piece(0, 1, "F2", false), piece(1, 2, "F1", false)],
            expected_state: ReplayState::Incomplete,
            expected_missing: vec![1],
        },
        ReplayTestCase {
            description: "unknown fingerprint completes with unknown",
            required: Some("F2"),
            coverage: vec![piece(0, 2, "F2", true)],
            expected_state: ReplayState::CompleteWithUnknownFingerprints,
            expected_missing: Vec::new(),
        },
    ];

    for test_case in test_cases {
        let projection = project_replay(
            ReplayVersions {
                required: test_case.required,
                current: "F2",
            },
            &[interval(0, 1), interval(1, 2)],
            &test_case.coverage,
        );
        assert_eq!(
            (projection.state, projection.missing),
            (test_case.expected_state, test_case.expected_missing),
            "{}",
            test_case.description
        );
    }
}
