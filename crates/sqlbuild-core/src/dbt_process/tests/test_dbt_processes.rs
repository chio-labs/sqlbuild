#![cfg(unix)]

use std::path::Path;

use crate::dbt_process::main::dbt_process_returncode::dbt_process_returncode;
use crate::dbt_process::main::run_dbt_process::run_dbt_process;
use crate::dbt_process::main::spawn_dbt_json_process::spawn_dbt_json_process;
use crate::dbt_process::main::stop_dbt_process::stop_dbt_process;
use crate::dbt_process::tests::helpers::{collected_lines, shell};
use crate::dbt_process::tests::test_types::{
    CapturedProcessTestCase, LaunchFailureTestCase, StopProcessTestCase, StreamedProcessTestCase,
};

#[test]
fn given_dbt_command_when_captured_then_output_and_exit_code_match_python_text_mode() {
    let test_cases = [
        CapturedProcessTestCase {
            description: "a clean exit keeps both streams with universal newlines",
            script: "printf 'one\\r\\ntwo\\r'; printf 'warn\\n' >&2",
            expected_returncode: 0,
            expected_stdout: "one\ntwo\n",
            expected_stderr: "warn\n",
        },
        CapturedProcessTestCase {
            description: "a failing exit reports its code",
            script: "exit 3",
            expected_returncode: 3,
            expected_stdout: "",
            expected_stderr: "",
        },
        CapturedProcessTestCase {
            description: "a signalled process reports the negated signal",
            script: "kill -TERM $$",
            expected_returncode: -15,
            expected_stdout: "",
            expected_stderr: "",
        },
    ];
    for test_case in test_cases {
        let output = run_dbt_process(&shell(test_case.script), None).expect("the shell runs");

        assert_eq!(
            output.returncode, test_case.expected_returncode,
            "{}",
            test_case.description
        );
        assert_eq!(
            output.stdout, test_case.expected_stdout,
            "{}",
            test_case.description
        );
        assert_eq!(
            output.stderr, test_case.expected_stderr,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_missing_dbt_executable_when_run_then_launch_error_is_not_found() {
    let test_cases = [LaunchFailureTestCase {
        description: "a missing program cannot start",
        program: "/nonexistent/dbt",
        expected_kind: std::io::ErrorKind::NotFound,
    }];
    for test_case in test_cases {
        let error = run_dbt_process(&[test_case.program.to_owned()], None).expect_err("no binary");

        assert_eq!(
            error.kind(),
            test_case.expected_kind,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_dbt_json_process_when_streamed_then_lines_merge_both_streams_with_json_env() {
    let test_cases = [
        StreamedProcessTestCase {
            description: "stdout and stderr share one stream with the JSON environment",
            script: "echo \"$DBT_LOG_FORMAT $PYTHONUNBUFFERED ${DBT_TARGET_PATH:-none}\"; echo err >&2; printf tail",
            target_path: None,
            expected_lines: vec!["json 1 none\n", "err\n", "tail"],
            expected_returncode: 0,
        },
        StreamedProcessTestCase {
            description: "a target path sets the target and log folders",
            script: "echo \"$DBT_TARGET_PATH $DBT_LOG_PATH\"; exit 4",
            target_path: Some("/tmp/target"),
            expected_lines: vec!["/tmp/target /tmp/target\n"],
            expected_returncode: 4,
        },
    ];
    for test_case in test_cases {
        let mut process = spawn_dbt_json_process(
            &shell(test_case.script),
            (None, test_case.target_path.map(Path::new)),
        )
        .expect("the shell starts");
        let lines: Vec<String> = collected_lines(&mut process);

        assert_eq!(lines, test_case.expected_lines, "{}", test_case.description);
        assert_eq!(
            dbt_process_returncode(&mut process.child).expect("waitable"),
            test_case.expected_returncode,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_running_dbt_process_when_stopped_then_terminate_is_requested_and_child_is_reaped() {
    let test_cases = [
        StopProcessTestCase {
            description: "a running process is asked to terminate, then killed and reaped",
            script: "exec sleep 30",
            settle: std::time::Duration::ZERO,
            expected_terminate_requests: 1,
        },
        StopProcessTestCase {
            description: "an exited process is only reaped",
            script: "exit 0",
            settle: std::time::Duration::from_millis(200),
            expected_terminate_requests: 0,
        },
    ];
    for test_case in test_cases {
        let process =
            spawn_dbt_json_process(&shell(test_case.script), (None, None)).expect("starts");
        std::thread::sleep(test_case.settle);
        let mut requests: Vec<u32> = Vec::new();

        let mut child = stop_dbt_process(process.child, |pid| requests.push(pid));

        assert_eq!(
            requests.len(),
            test_case.expected_terminate_requests,
            "{}",
            test_case.description
        );
        assert!(
            child.try_wait().expect("waitable").is_some(),
            "{}",
            test_case.description
        );
    }
}
