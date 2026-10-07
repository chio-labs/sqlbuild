use crate::models::ReadFailure;
use crate::yaml_files::models::YamlFileOutcome;
use crate::yaml_files::tests::helpers::{file_outcome, owned_failure, text_failure};
use crate::yaml_files::tests::test_types::{YamlFileTestCase, YamlTextTestCase};
use sqlbuild_config::models::ConfigValue;
use std::mem::discriminant;

#[test]
fn given_yaml_files_when_loading_then_each_file_loads_or_fails() {
    let test_cases = [
        YamlFileTestCase {
            description: "a plain mapping loads",
            contents: b"sources:\n  - name: orders\n",
            expected_outcome: YamlFileOutcome::Loaded {
                contents: String::new(),
                value: ConfigValue::Null,
            },
        },
        YamlFileTestCase {
            description: "invalid YAML fails",
            contents: b"sources: [\n",
            expected_outcome: YamlFileOutcome::Failed(crate::models::DiscoveryFailure::new(
                crate::models::FailureKind::Source,
                String::new(),
            )),
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            discriminant(&file_outcome(test_case.contents)),
            discriminant(&test_case.expected_outcome),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_undecodable_yaml_file_when_loading_then_python_decode_error_is_reported() {
    let test_cases = [
        YamlFileTestCase {
            description: "an invalid start byte",
            contents: b"name: \xff\n",
            expected_outcome: YamlFileOutcome::Unreadable(ReadFailure::Decode {
                bytes: b"name: \xff\n".to_vec(),
                start: 6,
                end: 7,
                reason: "invalid start byte",
            }),
        },
        YamlFileTestCase {
            description: "a truncated sequence at the end",
            contents: b"name: \xe2\x82",
            expected_outcome: YamlFileOutcome::Unreadable(ReadFailure::Decode {
                bytes: b"name: \xe2\x82".to_vec(),
                start: 6,
                end: 8,
                reason: "unexpected end of data",
            }),
        },
        YamlFileTestCase {
            description: "an invalid continuation byte",
            contents: b"name: \xe2\x82x",
            expected_outcome: YamlFileOutcome::Unreadable(ReadFailure::Decode {
                bytes: b"name: \xe2\x82x".to_vec(),
                start: 6,
                end: 8,
                reason: "invalid continuation byte",
            }),
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            file_outcome(test_case.contents),
            test_case.expected_outcome,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_yaml_text_when_loading_then_failures_name_file_position_and_construct() {
    let test_cases = [
        YamlTextTestCase {
            description: "common forms load",
            text: "sources:\n  - name: orders\n    description: |\n      Raw orders.\n    meta: &m {a: 1}\n    other:\n      <<: *m\n",
            expected_failure: None,
        },
        YamlTextTestCase {
            description: "an unclosed flow sequence is invalid YAML",
            text: "sources: [\n",
            expected_failure: Some((
                "project/sources/orders.yml contains invalid YAML at line 2, column 1: while \
                 parsing a node, did not find expected node content",
                None,
            )),
        },
        YamlTextTestCase {
            description: "a set tag is unsupported at its node",
            text: "sources:\n  - name: orders\n    meta: !!set {a: null}\n",
            expected_failure: Some((
                "project/sources/orders.yml uses YAML that SQLBuild does not support at line 3, \
                 column 17: values tagged !!set",
                Some(
                    "SQLBuild reads plain YAML: block and flow mappings and sequences, plain and \
                     quoted scalars, literal and folded block scalars, anchors, aliases and merge \
                     keys. Rewrite this part in one of those forms.",
                ),
            )),
        },
        YamlTextTestCase {
            description: "a tab is unsupported at its character",
            text: "sources:\n  - name: \"a\tb\"\n",
            expected_failure: Some((
                "project/sources/orders.yml uses YAML that SQLBuild does not support at line 2, \
                 column 13: tab characters",
                Some(
                    "SQLBuild reads plain YAML: block and flow mappings and sequences, plain and \
                     quoted scalars, literal and folded block scalars, anchors, aliases and merge \
                     keys. Rewrite this part in one of those forms.",
                ),
            )),
        },
        YamlTextTestCase {
            description: "a directive is unsupported at its line",
            text: "%YAML 1.1\n---\nsources: []\n",
            expected_failure: Some((
                "project/sources/orders.yml uses YAML that SQLBuild does not support at line 1, \
                 column 1: %YAML and %TAG directives",
                Some(
                    "SQLBuild reads plain YAML: block and flow mappings and sequences, plain and \
                     quoted scalars, literal and folded block scalars, anchors, aliases and merge \
                     keys. Rewrite this part in one of those forms.",
                ),
            )),
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            text_failure(test_case.text),
            owned_failure(test_case.expected_failure),
            "{}",
            test_case.description
        );
    }
}
