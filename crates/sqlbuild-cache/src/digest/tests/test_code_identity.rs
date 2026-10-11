use crate::digest::main::compiled_code_identity::compiled_code_identity;
use crate::digest::main::installed_code_identity::installed_code_identity;
use crate::digest::tests::helpers::write_package;
use crate::digest::tests::test_types::{
    CompiledCodeIdentityTestCase, InstalledCodeIdentityTestCase,
};

const PACKAGE_FILES: &[(&str, &str)] = &[
    ("a.py", "x"),
    ("pkg/b.so", "yy"),
    ("pkg/__pycache__/c.py", "z"),
    ("pkg/sub/d.pyd", "www"),
    (".py", "hidden"),
    ("e.txt", "t"),
    ("f.tar.py", "ff"),
    ("pkg/sub/\u{e9}.py", "u"),
];
const FACTS: &[&str] = &["1.0", "2.0", "3", "CPython", "3.12"];

#[cfg(unix)]
#[test]
fn given_package_tree_when_identifying_installed_code_then_python_digest_is_reproduced() {
    let test_cases = [
        InstalledCodeIdentityTestCase {
            description: "an editable install hashes sources, skipping bytecode, links and others",
            files: PACKAGE_FILES,
            facts: FACTS,
            editable: true,
            expected_identity: "7dba163ff7f85f33293d30ea8a4460b61242b487f65007b171dd7ec8831c22dd",
        },
        InstalledCodeIdentityTestCase {
            description: "a released install hashes only its facts",
            files: PACKAGE_FILES,
            facts: FACTS,
            editable: false,
            expected_identity: "3cd1c8ecd7d241204a1dcebdf9dd0ce4a39c6c64a6403ee6e85a2315075477df",
        },
    ];
    for test_case in test_cases {
        let directory = tempfile::tempdir().expect("a temporary folder");
        write_package(directory.path(), test_case.files);
        let facts: Vec<String> = test_case
            .facts
            .iter()
            .map(|fact| (*fact).to_owned())
            .collect();
        let root = test_case.editable.then_some(directory.path());

        assert_eq!(
            installed_code_identity(&facts, root),
            test_case.expected_identity,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_installed_and_build_identities_when_combining_then_python_digest_is_reproduced() {
    let test_cases = [CompiledCodeIdentityTestCase {
        description: "installed and build identities joined by NUL",
        installed: "abc",
        build_identity: "build-1",
        expected_identity: "b01e2fee4d9cd31dbd7d2ded6d49674d084cf9708e297905c02eb7645ebf015d",
    }];
    for test_case in test_cases {
        assert_eq!(
            compiled_code_identity(test_case.installed, test_case.build_identity),
            test_case.expected_identity,
            "{}",
            test_case.description
        );
    }
}
