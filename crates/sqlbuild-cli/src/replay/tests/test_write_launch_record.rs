use std::fs;

use crate::replay::main::write_launch_record::write_launch_record;
use crate::replay::tests::helpers::{existing_records, names};
use crate::replay::tests::test_types::LaunchRecordWriteTestCase;

#[test]
fn given_record_directory_when_writing_then_record_replaces_atomically_and_oldest_are_pruned() {
    let test_cases = [
        LaunchRecordWriteTestCase {
            description: "first record creates its directory",
            existing_records: 0,
            expected_names: vec!["new.json".to_owned()],
        },
        LaunchRecordWriteTestCase {
            description: "the oldest record beyond the limit is pruned",
            existing_records: 32,
            expected_names: (1..32)
                .map(|index| format!("{index:03}.json"))
                .chain(["new.json".to_owned()])
                .collect(),
        },
    ];
    for test_case in test_cases {
        let root = tempfile::tempdir().expect("temporary directory");
        let directory = root.path().join("target/cache/launcher-v1");
        existing_records(&directory, test_case.existing_records);
        let path = directory.join("new.json");

        write_launch_record(&path, "{\"format\": 1}").expect("write");

        assert_eq!(
            fs::read_to_string(&path).expect("read"),
            "{\"format\": 1}",
            "{}",
            test_case.description
        );
        assert_eq!(
            names(&directory),
            test_case.expected_names,
            "{}",
            test_case.description
        );
    }
}
