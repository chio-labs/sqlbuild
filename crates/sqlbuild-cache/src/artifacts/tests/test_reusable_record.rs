use crate::artifacts::main::new_sql_test_record::new_sql_test_record;
use crate::artifacts::main::reusable_sql_test_record::reusable_sql_test_record;
use crate::artifacts::models::SqlTestRecordMiss;
use crate::artifacts::tests::helpers::{bump_mtime, place};
use crate::artifacts::tests::test_types::ReusableRecordTestCase;

const IDENTITY: &str = "identity-1";

#[test]
fn given_recorded_artifact_when_checking_reuse_then_reports_why_it_missed() {
    let test_cases = [
        ReusableRecordTestCase {
            description: "an unchanged artifact is kept",
            change: |_| {},
            identity: IDENTITY,
            expected_outcome: Ok(()),
        },
        ReusableRecordTestCase {
            description: "a touched artifact with the same bytes is kept",
            change: bump_mtime,
            identity: IDENTITY,
            expected_outcome: Ok(()),
        },
        ReusableRecordTestCase {
            description: "a new identity misses",
            change: |_| {},
            identity: "identity-2",
            expected_outcome: Err(SqlTestRecordMiss::IdentityChanged),
        },
        ReusableRecordTestCase {
            description: "a deleted artifact misses",
            change: |root| std::fs::remove_file(root.join("t.sql")).expect("removed"),
            identity: IDENTITY,
            expected_outcome: Err(SqlTestRecordMiss::ArtifactMissing),
        },
        ReusableRecordTestCase {
            description: "a resized artifact misses",
            change: |root| place(&root.join("t.sql"), b"select 10\n"),
            identity: IDENTITY,
            expected_outcome: Err(SqlTestRecordMiss::SizeChanged),
        },
        ReusableRecordTestCase {
            description: "same-size new bytes miss",
            change: |root| {
                place(&root.join("t.sql"), b"select 2\n");
                bump_mtime(root);
            },
            identity: IDENTITY,
            expected_outcome: Err(SqlTestRecordMiss::ContentChanged),
        },
    ];
    for test_case in test_cases {
        let root = tempfile::tempdir().expect("tests folder");
        place(&root.path().join("t.sql"), b"select 1\n");
        let record = new_sql_test_record(root.path(), &root.path().join("t.sql"), IDENTITY)
            .expect("recorded artifact");
        (test_case.change)(root.path());

        let outcome = reusable_sql_test_record(root.path(), &record, test_case.identity);

        assert_eq!(
            outcome.map(|_| ()),
            test_case.expected_outcome,
            "{}",
            test_case.description
        );
    }
}
