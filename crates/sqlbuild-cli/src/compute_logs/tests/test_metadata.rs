use std::path::PathBuf;
use std::time::{Duration, UNIX_EPOCH};

use crate::compute_logs::_helpers::metadata::metadata_json;
use crate::compute_logs::_helpers::timestamps::{parse_iso_instant, utc_timestamp};
use crate::compute_logs::models::{CaptureEnd, CaptureStart};
use crate::compute_logs::tests::test_types::{MetadataTestCase, TimestampTestCase};

const STARTED_MICROSECONDS: u64 = 1_791_732_481_125_950;

#[test]
fn given_utc_instant_when_formatting_then_matches_python_isoformat_and_parses_back() {
    let test_cases = [
        TimestampTestCase {
            description: "microseconds are written with six digits",
            microseconds: 1_791_732_481_125_950,
            expected_timestamp: "2026-10-11T15:28:01.125950Z",
        },
        TimestampTestCase {
            description: "a whole second omits the fraction",
            microseconds: 1_791_732_482_000_000,
            expected_timestamp: "2026-10-11T15:28:02Z",
        },
        TimestampTestCase {
            description: "a leap day keeps one microsecond",
            microseconds: 951_782_400_000_001,
            expected_timestamp: "2000-02-29T00:00:00.000001Z",
        },
        TimestampTestCase {
            description: "an instant before the epoch",
            microseconds: -1_000_000,
            expected_timestamp: "1969-12-31T23:59:59Z",
        },
    ];

    for test_case in test_cases {
        let timestamp = utc_timestamp(test_case.microseconds);

        assert_eq!(
            (
                timestamp.as_str(),
                parse_iso_instant(&timestamp.replace('Z', "+00:00")),
            ),
            (
                test_case.expected_timestamp,
                Some((test_case.microseconds, true))
            ),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_capture_when_writing_metadata_then_bytes_match_python_metadata_to_json() {
    let test_cases = [
        MetadataTestCase {
            description: "an open capture",
            target: None,
            end: None,
            expected_json: "{\"capture_date\":\"2026-10-11\",\"command\":\"compile\",\"format_version\":1,\"invocation_id\":\"abc\",\"project_dir\":\"/p/\u{e9}\",\"run_id\":null,\"started_at\":\"2026-10-11T15:28:01.125950Z\",\"target\":null}\n",
        },
        MetadataTestCase {
            description: "a completed capture",
            target: Some("dev"),
            end: Some((1_791_732_482, 1, 3, 4)),
            expected_json: "{\"capture_date\":\"2026-10-11\",\"command\":\"compile\",\"completed_at\":\"2026-10-11T15:28:02Z\",\"diagnostics_bytes\":0,\"exit_code\":1,\"format_version\":1,\"invocation_id\":\"abc\",\"project_dir\":\"/p/\u{e9}\",\"run_id\":null,\"started_at\":\"2026-10-11T15:28:01.125950Z\",\"stderr_bytes\":4,\"stdout_bytes\":3,\"target\":\"dev\"}\n",
        },
    ];

    for test_case in test_cases {
        let start = CaptureStart {
            root: PathBuf::from("/p/logs"),
            command: "compile".to_owned(),
            project_dir: "/p/\u{e9}".to_owned(),
            target: test_case.target.map(str::to_owned),
            started_at: UNIX_EPOCH + Duration::from_micros(STARTED_MICROSECONDS),
        };
        let end = test_case.end.map(|(completed, exit_code, stdout, stderr)| {
            (
                CaptureEnd {
                    stdout: vec![0; stdout],
                    stderr: vec![0; stderr],
                    exit_code,
                },
                completed * 1_000_000,
                (stdout, stderr, 0),
            )
        });

        let json = metadata_json(
            (&start, "abc"),
            end.as_ref()
                .map(|(end, completed, counts)| (end, *completed, *counts)),
        );

        assert_eq!(json, test_case.expected_json, "{}", test_case.description);
    }
}
