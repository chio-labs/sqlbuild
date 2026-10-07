use crate::tree::models::ProjectTree;
use crate::yaml_files::main::load_yaml_files::load_yaml_files;
use crate::yaml_files::models::YamlFileOutcome;
use crate::yaml_files::tests::test_types::YamlFileTestCase;

use crate::yaml_files::tests::helpers::python;
use sqlbuild_config::models::ConfigValue;
use std::mem::discriminant;

#[test]
fn given_yaml_files_when_loading_then_each_file_loads_or_defers() {
    let test_cases = [
        YamlFileTestCase {
            description: "a plain mapping loads natively",
            contents: b"sources:\n  - name: orders\n",
            expected_outcome: YamlFileOutcome::Loaded {
                contents: String::new(),
                value: ConfigValue::Null,
            },
        },
        YamlFileTestCase {
            description: "invalid YAML is left to Python for its exact error",
            contents: b"sources: [\n",
            expected_outcome: python(),
        },
        YamlFileTestCase {
            description: "a Python-only tag is left to Python",
            contents: b"value: !!set {a: null}\n",
            expected_outcome: python(),
        },
        YamlFileTestCase {
            description: "undecodable bytes are re-read by Python",
            contents: b"name: \xff\n",
            expected_outcome: YamlFileOutcome::Unreadable,
        },
    ];
    for test_case in test_cases {
        let project = tempfile::tempdir().expect("temporary project");
        std::fs::write(project.path().join("file.yml"), test_case.contents).expect("file");
        let outcomes = load_yaml_files(&ProjectTree::new(project.path()), &["file.yml".to_owned()])
            .expect("no deferral");
        assert_eq!(
            outcomes.iter().map(discriminant).collect::<Vec<_>>(),
            vec![discriminant(&test_case.expected_outcome)],
            "{}",
            test_case.description
        );
    }
}
