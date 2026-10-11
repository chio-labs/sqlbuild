use crate::compute_logs::constants::DEFAULT_RETENTION_COUNT;
use crate::compute_logs::main::finish_capture::finish_capture;
use crate::compute_logs::main::start_capture::start_capture;
use crate::compute_logs::models::CaptureEnd;
use crate::compute_logs::tests::helpers::{capture_start, complete_captures};
use crate::compute_logs::tests::test_types::PruneTestCase;

#[test]
fn given_finished_command_when_capturing_then_streams_metadata_and_pruning_match_python() {
    let test_cases = [
        PruneTestCase {
            description: "below the retention count every capture stays",
            existing: 2,
            expected_complete: 3,
        },
        PruneTestCase {
            description: "the oldest captures beyond the retention count are deleted",
            existing: DEFAULT_RETENTION_COUNT + 2,
            expected_complete: DEFAULT_RETENTION_COUNT,
        },
    ];

    for test_case in test_cases {
        let root = tempfile::tempdir().expect("temporary log root");
        let end = CaptureEnd {
            stdout: b"Compile ready\n".to_vec(),
            stderr: b"Inputs unchanged\n".to_vec(),
            exit_code: 0,
        };
        for offset in 0..test_case.existing {
            let capture = start_capture(capture_start(root.path(), 60 + offset as u64))
                .expect("capture starts");
            finish_capture(capture, &end).expect("capture finishes");
        }

        let capture = start_capture(capture_start(root.path(), 0)).expect("capture starts");
        let directory = capture.directory.clone();
        finish_capture(capture, &end).expect("capture finishes");

        assert_eq!(
            (
                std::fs::read(directory.join("stdout.log")).expect("stdout log"),
                std::fs::read(directory.join("stderr.log")).expect("stderr log"),
                std::fs::read(directory.join("diagnostics.jsonl")).expect("diagnostics log"),
                complete_captures(root.path()).len(),
            ),
            (
                end.stdout.clone(),
                end.stderr.clone(),
                Vec::new(),
                test_case.expected_complete,
            ),
            "{}",
            test_case.description
        );
    }
}
