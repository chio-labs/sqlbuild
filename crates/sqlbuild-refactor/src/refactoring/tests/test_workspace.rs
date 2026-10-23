use crate::refactoring::_helpers::files::workspace::{commit_changes, write_staged_changes};
use crate::refactoring::models::FileChange;
use crate::refactoring::tests::helpers::{moved, owned_pairs, tree, write_files};
use crate::refactoring::tests::test_types::StagedCommitOrderTestCase;
use crate::refactoring::types::Originals;

#[test]
fn given_changes_when_staging_and_committing_then_both_leave_the_same_files() {
    let test_cases = [
        StagedCommitOrderTestCase {
            description: "a plain move leaves only the destination",
            files: &[("a/one.sql", "one"), ("a/two.sql", "two")],
            changes: &[("a/one.sql", "b/one.sql")],
            expected_files: &[("a/two.sql", "two"), ("b/one.sql", "one")],
        },
        StagedCommitOrderTestCase {
            description: "a file one change leaves and another moves onto is kept",
            files: &[("a.sql", "first"), ("b.sql", "second")],
            changes: &[("a.sql", "b.sql"), ("b.sql", "c.sql")],
            expected_files: &[("b.sql", "first"), ("c.sql", "second")],
        },
        StagedCommitOrderTestCase {
            description: "the order of chained changes does not matter",
            files: &[("a.sql", "first"), ("b.sql", "second")],
            changes: &[("b.sql", "c.sql"), ("a.sql", "b.sql")],
            expected_files: &[("b.sql", "first"), ("c.sql", "second")],
        },
    ];
    for test_case in test_cases {
        let changes: Vec<FileChange> = test_case
            .changes
            .iter()
            .map(|(source, destination)| moved(source, destination))
            .collect();
        let originals: Originals = test_case
            .files
            .iter()
            .filter(|(path, _)| test_case.changes.iter().any(|(source, _)| source == path))
            .map(|(path, text)| ((*path).to_owned(), (*text).to_owned()))
            .collect();
        let paths: Vec<&str> = test_case
            .files
            .iter()
            .map(|(path, _)| *path)
            .chain(
                test_case
                    .changes
                    .iter()
                    .map(|(_, destination)| *destination),
            )
            .collect();
        let (staged, committed) = (tempfile::tempdir(), tempfile::tempdir());
        let (Ok(staged), Ok(committed)) = (staged, committed) else {
            panic!(
                "{}: cannot create temporary directories",
                test_case.description
            );
        };
        for root in [staged.path(), committed.path()] {
            assert!(
                write_files(root, test_case.files).is_ok(),
                "{}",
                test_case.description
            );
        }

        let staging = write_staged_changes(staged.path(), &originals, &changes);
        let commit = commit_changes(committed.path(), &originals, &changes);

        assert!(staging.is_ok(), "{}: {staging:?}", test_case.description);
        assert!(commit.is_ok(), "{}: {commit:?}", test_case.description);
        assert_eq!(
            (tree(staged.path(), &paths), tree(committed.path(), &paths)),
            (
                owned_pairs(test_case.expected_files),
                owned_pairs(test_case.expected_files)
            ),
            "{}",
            test_case.description
        );
    }
}
