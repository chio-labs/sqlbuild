use crate::rule_evidence::main::allowed_custom_rule_import::allowed_custom_rule_import;
use crate::rule_evidence::main::disallowed_import::disallowed_import;
use crate::rule_evidence::models::{DisallowedImport, UnparsedSource};
use crate::rule_evidence::tests::test_types::{AllowedImportTestCase, DisallowedImportTestCase};

const PYTHON: (u8, u8) = (3, 12);

#[test]
fn given_module_names_when_checked_then_only_allowlisted_roots_and_submodules_pass() {
    let test_cases = [
        AllowedImportTestCase {
            description: "an allowed root",
            module: "json",
            expected_allowed: true,
        },
        AllowedImportTestCase {
            description: "an allowed submodule",
            module: "json.decoder",
            expected_allowed: true,
        },
        AllowedImportTestCase {
            description: "an allowed dotted root",
            module: "sqlbuild.rules",
            expected_allowed: true,
        },
        AllowedImportTestCase {
            description: "a submodule of an allowed package",
            module: "collections.abc",
            expected_allowed: true,
        },
        AllowedImportTestCase {
            description: "a longer name sharing a prefix",
            module: "jsonx",
            expected_allowed: false,
        },
        AllowedImportTestCase {
            description: "the parent of an allowed dotted root",
            module: "sqlbuild",
            expected_allowed: false,
        },
        AllowedImportTestCase {
            description: "an empty module",
            module: "",
            expected_allowed: false,
        },
        AllowedImportTestCase {
            description: "a trailing dot",
            module: "json.",
            expected_allowed: true,
        },
        AllowedImportTestCase {
            description: "a leading dot",
            module: ".json",
            expected_allowed: false,
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            allowed_custom_rule_import(test_case.module),
            test_case.expected_allowed,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_rule_sources_when_scanned_then_the_first_disallowed_import_in_walk_order_is_found() {
    let test_cases = [
        DisallowedImportTestCase {
            description: "only allowed and relative imports",
            source: "import json\nfrom . import helpers\nfrom re import x\n",
            expected_import: Ok(None),
        },
        DisallowedImportTestCase {
            description: "the first disallowed top-level import",
            source: "import json\nimport os\nimport subprocess\n",
            expected_import: Ok(Some(DisallowedImport {
                line: 2,
                module: "os".to_owned(),
            })),
        },
        DisallowedImportTestCase {
            description: "top-level statements are visited before nested ones",
            source: "def f():\n    import socket\n\nfrom urllib import request\n",
            expected_import: Ok(Some(DisallowedImport {
                line: 4,
                module: "urllib".to_owned(),
            })),
        },
        DisallowedImportTestCase {
            description: "each alias of one statement in order",
            source: "import json, os.path as p, re\n",
            expected_import: Ok(Some(DisallowedImport {
                line: 1,
                module: "os.path".to_owned(),
            })),
        },
        DisallowedImportTestCase {
            description: "CRLF lines and continuations",
            source: "import json\r\n\r\nimport \\\n    os\r\n",
            expected_import: Ok(Some(DisallowedImport {
                line: 3,
                module: "os".to_owned(),
            })),
        },
        DisallowedImportTestCase {
            description: "a syntax error",
            source: "def broken(:\n",
            expected_import: Err(UnparsedSource),
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            disallowed_import(test_case.source, PYTHON),
            test_case.expected_import,
            "{}",
            test_case.description
        );
    }
}
