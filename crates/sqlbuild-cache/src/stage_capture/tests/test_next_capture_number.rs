use crate::stage_capture::main::next_capture_number::next_capture_number;
use crate::stage_capture::tests::test_types::CaptureNumberTestCase;

#[test]
fn given_capture_directory_files_when_numbering_then_counts_numbered_captures() {
    let test_cases = [
        CaptureNumberTestCase {
            description: "an empty directory starts at one",
            file_names: &[],
            expected_number: 1,
        },
        CaptureNumberTestCase {
            description: "numbered captures advance the sequence",
            file_names: &["001-discovery.json", "002-plan_output.json"],
            expected_number: 3,
        },
        CaptureNumberTestCase {
            description: "other files are ignored",
            file_names: &[
                "001-discovery.json",
                "notes.txt",
                "x-1.json",
                ".001-a.json.tmp",
            ],
            expected_number: 2,
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            next_capture_number(test_case.file_names.iter().copied()),
            test_case.expected_number,
            "{}",
            test_case.description
        );
    }
}
