use std::ffi::OsString;
use std::path::{Path, PathBuf};

use crate::launcher::_helpers::launch_key::{launch_key, launch_record_path};
use crate::launcher::tests::test_types::{LaunchKeyTestCase, LaunchRecordPathTestCase};

#[test]
fn given_arguments_when_locating_launch_record_then_only_exact_project_options_count() {
    let test_cases = [
        LaunchRecordPathTestCase {
            description: "no project option uses the working directory",
            arguments: &["compile", "--json"],
            expected_project: Some("/work"),
        },
        LaunchRecordPathTestCase {
            description: "the last exact option wins, with or without an equals sign",
            arguments: &[
                "--project-dir",
                "first",
                "compile",
                "--sqb-project-dir=/shop",
            ],
            expected_project: Some("/shop"),
        },
        LaunchRecordPathTestCase {
            description: "a relative project joins the working directory",
            arguments: &["compile", "--project-dir", "shop"],
            expected_project: Some("/work/shop"),
        },
        LaunchRecordPathTestCase {
            description: "an abbreviation argparse would expand is not guessed",
            arguments: &["compile", "--project", "shop"],
            expected_project: None,
        },
        LaunchRecordPathTestCase {
            description: "a project option without its value is not guessed",
            arguments: &["compile", "--project-dir"],
            expected_project: None,
        },
    ];

    for test_case in test_cases {
        let arguments: Vec<OsString> = test_case.arguments.iter().map(OsString::from).collect();

        let path = launch_record_path(&arguments, Path::new("/work"), "key");

        assert_eq!(
            path,
            test_case
                .expected_project
                .map(|project| PathBuf::from(project).join("target/cache/launcher-v1/key.json")),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_changed_arguments_or_directory_when_keying_then_the_launch_key_changes() {
    let test_cases = [
        LaunchKeyTestCase {
            description: "the same invocation shares its key",
            arguments: &["compile"],
            cwd: "/work",
            expected_same: true,
        },
        LaunchKeyTestCase {
            description: "another argument changes the key",
            arguments: &["compile", "--json"],
            cwd: "/work",
            expected_same: false,
        },
        LaunchKeyTestCase {
            description: "another working directory changes the key",
            arguments: &["compile"],
            cwd: "/elsewhere",
            expected_same: false,
        },
    ];
    let program = std::env::current_exe().expect("test program");
    let base = launch_key(
        &program,
        &program,
        &[OsString::from("compile")],
        Path::new("/work"),
    );

    for test_case in test_cases {
        let arguments: Vec<OsString> = test_case.arguments.iter().map(OsString::from).collect();

        let key = launch_key(&program, &program, &arguments, Path::new(test_case.cwd));

        assert_eq!(
            key == base,
            test_case.expected_same,
            "{}",
            test_case.description
        );
    }
}
