use std::ffi::{OsStr, OsString};
use std::path::Path;

use crate::launcher::_helpers::hosting::{HostMode, host_mode, hosted_arguments};
use crate::launcher::tests::test_types::{HostModeTestCase, HostedArgumentsTestCase};

#[test]
fn given_host_mode_values_when_reading_then_only_the_two_modes_or_unset_are_accepted() {
    let test_cases = [
        HostModeTestCase {
            description: "unset tries the process first",
            value: None,
            expected_mode: Some(HostMode::Automatic),
        },
        HostModeTestCase {
            description: "empty is the same as unset",
            value: Some(""),
            expected_mode: Some(HostMode::Automatic),
        },
        HostModeTestCase {
            description: "embedded requires the process",
            value: Some("embedded"),
            expected_mode: Some(HostMode::Embedded),
        },
        HostModeTestCase {
            description: "exec always runs the script",
            value: Some("exec"),
            expected_mode: Some(HostMode::Exec),
        },
        HostModeTestCase {
            description: "other spellings are rejected",
            value: Some("Embedded"),
            expected_mode: None,
        },
    ];

    for test_case in test_cases {
        let mode: Option<HostMode> = host_mode(test_case.value.map(OsStr::new));

        assert_eq!(mode, test_case.expected_mode, "{}", test_case.description);
    }
}

#[test]
fn given_handed_arguments_when_hosting_then_python_runs_the_script_as_exec_would() {
    let test_cases = [HostedArgumentsTestCase {
        description: "the script, then the launch record option and the command",
        script: "/shop/.venv/bin/sqlbuild-python",
        handed: &[
            "--sqlbuild-launch-record=/shop/key.json",
            "compile",
            "--json",
        ],
        expected_arguments: &[
            "/shop/.venv/bin/sqlbuild-python",
            "--sqlbuild-launch-record=/shop/key.json",
            "compile",
            "--json",
        ],
    }];

    for test_case in test_cases {
        let handed: Vec<OsString> = test_case.handed.iter().map(OsString::from).collect();

        let arguments: Vec<OsString> = hosted_arguments(Path::new(test_case.script), &handed);

        assert_eq!(
            arguments,
            test_case
                .expected_arguments
                .iter()
                .map(OsString::from)
                .collect::<Vec<OsString>>(),
            "{}",
            test_case.description
        );
    }
}
