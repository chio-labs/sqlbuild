use std::path::PathBuf;

use crate::host::_helpers::script::script_interpreter;
use crate::host::tests::helpers::{link, rooted, temporary_root, write_executable};
use crate::host::tests::test_types::{LinkedScriptTestCase, ScriptTestCase};

#[test]
fn given_console_script_when_reading_interpreter_then_matches_what_exec_starts() {
    let test_cases = [
        ScriptTestCase {
            description: "a plain #! line names the interpreter",
            head: "#!/opt/shop/.venv/bin/python3\n# -*- coding: utf-8 -*-\nimport sys\n",
            expected_interpreter: Some("/opt/shop/.venv/bin/python3"),
        },
        ScriptTestCase {
            description: "trailing whitespace on the #! line is ignored",
            head: "#!/opt/shop/.venv/bin/python  \nimport sys\n",
            expected_interpreter: Some("/opt/shop/.venv/bin/python"),
        },
        ScriptTestCase {
            description: "an env lookup is not resolved",
            head: "#!/usr/bin/env python3\nimport sys\n",
            expected_interpreter: None,
        },
        ScriptTestCase {
            description: "interpreter arguments are not reproduced",
            head: "#!/usr/bin/python3 -E\nimport sys\n",
            expected_interpreter: None,
        },
        ScriptTestCase {
            description: "a relative interpreter is not guessed",
            head: "#!python\nimport sys\n",
            expected_interpreter: None,
        },
        ScriptTestCase {
            description: "uv's relocatable trampoline runs python in the resolved directory",
            head: "#!/bin/sh\n'''exec' \"$(dirname -- \"$(realpath -- \"$0\")\")\"/'python' \"$0\" \"$@\"\n' '''\n",
            expected_interpreter: Some("<root>/python"),
        },
        ScriptTestCase {
            description: "a single-quoted absolute trampoline interpreter",
            head: "#!/bin/sh\n'''exec' '/opt/long path/bin/python' \"$0\" \"$@\"\n' '''\n",
            expected_interpreter: Some("/opt/long path/bin/python"),
        },
        ScriptTestCase {
            description: "a double-quoted absolute trampoline interpreter",
            head: "#!/bin/sh\n'''exec' \"/opt/long path/bin/python\" \"$0\" \"$@\"\n' '''\n",
            expected_interpreter: Some("/opt/long path/bin/python"),
        },
        ScriptTestCase {
            description: "an unquoted absolute trampoline interpreter",
            head: "#!/bin/sh\n'''exec' /opt/shop/bin/python \"$0\" \"$@\"\n' '''\n",
            expected_interpreter: Some("/opt/shop/bin/python"),
        },
        ScriptTestCase {
            description: "a trampoline that expands variables is not guessed",
            head: "#!/bin/sh\n'''exec' \"$HOME/bin/python\" \"$0\" \"$@\"\n' '''\n",
            expected_interpreter: None,
        },
        ScriptTestCase {
            description: "a relocatable trampoline naming a path is not guessed",
            head: "#!/bin/sh\n'''exec' \"$(dirname -- \"$(realpath -- \"$0\")\")\"/'../python' \"$0\" \"$@\"\n' '''\n",
            expected_interpreter: None,
        },
        ScriptTestCase {
            description: "any other shell script is not guessed",
            head: "#!/bin/sh\nexec python -m shop \"$@\"\n",
            expected_interpreter: None,
        },
        ScriptTestCase {
            description: "a file without a #! line",
            head: "import sys\n",
            expected_interpreter: None,
        },
    ];

    for test_case in test_cases {
        let (_directory, root) = temporary_root();
        let script: PathBuf = root.join("sqlbuild-python");
        write_executable(&script, test_case.head);

        let interpreter: Result<PathBuf, ()> = script_interpreter(&script).map_err(drop);

        assert_eq!(
            interpreter,
            test_case
                .expected_interpreter
                .map(|expected| PathBuf::from(rooted(expected, &root)))
                .ok_or(()),
            "{}",
            test_case.description
        );
    }
}

#[cfg(unix)]
#[test]
fn given_linked_relocatable_script_when_reading_interpreter_then_uses_link_target_directory() {
    let test_cases = [LinkedScriptTestCase {
        description: "a tool's script linked into a shared bin directory",
        script: "tool/bin/sqlbuild-python",
        link: "bin/sqlbuild-python",
        head: "#!/bin/sh\n'''exec' \"$(dirname -- \"$(realpath -- \"$0\")\")\"/'python3' \"$0\" \"$@\"\n' '''\n",
        expected_interpreter: "<root>/tool/bin/python3",
    }];

    for test_case in test_cases {
        let (_directory, root) = temporary_root();
        write_executable(&root.join(test_case.script), test_case.head);
        let linked: PathBuf = link(&root, test_case.script, test_case.link);

        let interpreter: Result<PathBuf, String> = script_interpreter(&linked);

        assert_eq!(
            interpreter,
            Ok(PathBuf::from(rooted(test_case.expected_interpreter, &root))),
            "{}",
            test_case.description
        );
    }
}
