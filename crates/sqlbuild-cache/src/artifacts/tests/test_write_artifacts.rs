use crate::artifacts::errors::ArtifactError;
use crate::artifacts::main::write_artifacts::write_artifacts;
use crate::artifacts::tests::helpers::{batch, place};
use crate::artifacts::tests::test_types::{
    FirstFailureTestCase, RepeatedPathTestCase, WriteBatchTestCase,
};

#[test]
fn given_artifact_batch_when_written_then_every_file_matches_and_unchanged_files_are_counted() {
    let test_cases = [
        WriteBatchTestCase {
            description: "small sequential batch",
            file_count: 5,
            check_existing: true,
            existing_identical: &[1],
            existing_different: &[3],
            expected_written: 4,
            expected_unchanged: 1,
        },
        WriteBatchTestCase {
            description: "large parallel batch",
            file_count: 500,
            check_existing: true,
            existing_identical: &[0, 250, 499],
            existing_different: &[10, 400],
            expected_written: 497,
            expected_unchanged: 3,
        },
        WriteBatchTestCase {
            description: "parallel batch overwriting without checks",
            file_count: 200,
            check_existing: false,
            existing_identical: &[5],
            existing_different: &[6],
            expected_written: 200,
            expected_unchanged: 0,
        },
        WriteBatchTestCase {
            description: "parallel batch into an empty target",
            file_count: 64,
            check_existing: true,
            existing_identical: &[],
            existing_different: &[],
            expected_written: 64,
            expected_unchanged: 0,
        },
    ];
    for test_case in test_cases {
        let root = tempfile::tempdir().expect("target directory");
        let files = batch(root.path(), test_case.file_count);
        for &index in test_case.existing_identical {
            place(&files[index].0, &files[index].1);
        }
        for &index in test_case.existing_different {
            place(&files[index].0, b"stale\n");
        }
        let outcome = write_artifacts(&files, test_case.check_existing).expect("written batch");
        assert_eq!(
            outcome.written, test_case.expected_written,
            "{}",
            test_case.description
        );
        assert_eq!(
            outcome.unchanged, test_case.expected_unchanged,
            "{}",
            test_case.description
        );
        let matching = files
            .iter()
            .filter(|(path, contents)| std::fs::read(path).ok().as_ref() == Some(contents))
            .count();
        assert_eq!(matching, test_case.file_count, "{}", test_case.description);
    }
}

#[test]
fn given_several_non_utf8_existing_files_when_written_then_the_first_in_batch_order_is_reported() {
    let test_cases = [
        FirstFailureTestCase {
            description: "sequential batch",
            file_count: 10,
            failing: &[3, 9],
            expected_failing: 3,
        },
        FirstFailureTestCase {
            description: "parallel batch",
            file_count: 300,
            failing: &[100, 299],
            expected_failing: 100,
        },
    ];
    for test_case in test_cases {
        let root = tempfile::tempdir().expect("target directory");
        let files = batch(root.path(), test_case.file_count);
        for &index in test_case.failing {
            place(&files[index].0, &[0xff, 0xfe]);
        }
        let error = write_artifacts(&files, true).expect_err("non-UTF-8 existing artifact");
        assert!(
            matches!(
                &error,
                ArtifactError::ExistingNotUtf8 { path } if *path == files[test_case.expected_failing].0
            ),
            "{}: {error:?}",
            test_case.description
        );
    }
}

#[test]
fn given_repeated_artifact_path_when_written_then_the_last_queued_contents_win() {
    let test_cases = [RepeatedPathTestCase {
        description: "large batch repeating one path",
        file_count: 100,
        repeated: 2,
        expected_contents: b"select 'last'\n",
    }];
    for test_case in test_cases {
        let root = tempfile::tempdir().expect("target directory");
        let mut files = batch(root.path(), test_case.file_count);
        let repeated = files[test_case.repeated].0.clone();
        files.push((repeated.clone(), test_case.expected_contents.to_vec()));
        write_artifacts(&files, true).expect("written batch");
        assert_eq!(
            std::fs::read(&repeated).expect("repeated artifact"),
            test_case.expected_contents,
            "{}",
            test_case.description
        );
    }
}
