use crate::compute_logs::_helpers::files::publish_staged;
use crate::compute_logs::tests::test_types::PublicationTestCase;

#[test]
fn given_failing_staged_step_when_publishing_then_no_capture_directory_remains() {
    let test_cases = [
        PublicationTestCase {
            description: "a clean staging directory is published",
            blocking_entries: &[],
            expected_published: true,
            expected_entries: 1,
        },
        PublicationTestCase {
            description: "metadata that cannot replace its destination removes the staging",
            blocking_entries: &["metadata.json"],
            expected_published: false,
            expected_entries: 0,
        },
        PublicationTestCase {
            description: "a stream file that already exists removes the staging",
            blocking_entries: &["stderr.log"],
            expected_published: false,
            expected_entries: 0,
        },
    ];

    for test_case in test_cases {
        let date_directory = tempfile::tempdir().expect("temporary directory");
        let staging = date_directory.path().join(".capture.staging.tmp");
        let directory = date_directory.path().join("capture");
        std::fs::create_dir(&staging).expect("staging directory");
        for name in test_case.blocking_entries {
            std::fs::create_dir_all(staging.join(name).join("occupied")).expect("blocking entry");
        }

        let published = publish_staged(&staging, &directory, "{}\n").is_ok();
        let entries = std::fs::read_dir(date_directory.path())
            .map(Iterator::count)
            .unwrap_or_default();

        assert_eq!(
            (published, entries),
            (test_case.expected_published, test_case.expected_entries),
            "{}",
            test_case.description
        );
    }
}
