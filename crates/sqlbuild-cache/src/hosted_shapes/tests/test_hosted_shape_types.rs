use crate::hosted_shapes::constants::HOSTED_SHAPE_TYPES;
use crate::hosted_shapes::main::captured_shape_name::captured_shape_name;
use crate::hosted_shapes::tests::helpers::duplicates;
use crate::hosted_shapes::tests::test_types::{CapturedNameTestCase, HostedKeyTestCase};

#[test]
fn given_hosted_shape_table_when_keyed_then_every_native_and_python_name_is_unique() {
    let test_cases = [
        HostedKeyTestCase {
            description: "native class names",
            keys: HOSTED_SHAPE_TYPES
                .iter()
                .map(|(native, _)| *native)
                .collect(),
            expected_duplicates: Vec::new(),
        },
        HostedKeyTestCase {
            description: "qualified Python shape names",
            keys: HOSTED_SHAPE_TYPES
                .iter()
                .map(|(_, python)| *python)
                .collect(),
            expected_duplicates: Vec::new(),
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            duplicates(&test_case.keys),
            test_case.expected_duplicates,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_native_class_when_naming_its_capture_then_only_hosted_shapes_keep_a_python_name() {
    let test_cases = [
        CapturedNameTestCase {
            description: "a hosted planner record keeps its Python name",
            native: "sqlbuild._native:PlanOutput",
            expected_python: Some("sqlbuild.compiler.planner.models:PlanOutput"),
        },
        CapturedNameTestCase {
            description: "a native class hosting no shape has no Python name",
            native: "sqlbuild._native:NoSuchShape",
            expected_python: None,
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            captured_shape_name(test_case.native),
            test_case.expected_python,
            "{}",
            test_case.description
        );
    }
}
