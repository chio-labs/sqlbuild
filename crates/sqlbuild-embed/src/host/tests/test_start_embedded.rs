use std::ffi::OsString;
use std::path::PathBuf;

use crate::host::main::start_embedded::start_embedded;
use crate::host::models::EmbeddableInterpreter;
use crate::host::tests::helpers::temporary_root;
use crate::host::tests::test_types::StartTestCase;

#[test]
fn given_file_that_is_not_a_library_when_starting_then_nothing_runs_and_reason_is_returned() {
    let test_cases = [
        StartTestCase {
            description: "an empty file",
            library_contents: b"",
            expected_reason_prefix: "cannot load ",
        },
        StartTestCase {
            description: "a text file",
            library_contents: b"not a shared library\n",
            expected_reason_prefix: "cannot load ",
        },
    ];

    for test_case in test_cases {
        let (_directory, root) = temporary_root();
        let library: PathBuf = root.join("libpython3.12.so.1.0");
        std::fs::write(&library, test_case.library_contents).expect("library");
        let found = EmbeddableInterpreter {
            interpreter: root.join("python"),
            library,
            version: "3.12".to_owned(),
        };

        let started = start_embedded(&found, &[OsString::from("--help")], &[]);

        let reason: String = started.expect_err("cannot be loaded").reason;
        assert!(
            reason.starts_with(test_case.expected_reason_prefix),
            "{}: {reason}",
            test_case.description
        );
    }
}
