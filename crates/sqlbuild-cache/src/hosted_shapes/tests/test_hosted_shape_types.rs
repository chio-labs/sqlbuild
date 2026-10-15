use crate::hosted_shapes::constants::HOSTED_SHAPE_TYPES;
use crate::hosted_shapes::main::hosted_native_name::hosted_native_name;
use crate::hosted_shapes::tests::helpers::duplicates;
use crate::hosted_shapes::tests::test_types::{HostedKeyTestCase, NativeNameTestCase};

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
fn given_python_shape_when_resolving_then_only_its_own_module_selects_the_native_class() {
    let test_cases = [
        NativeNameTestCase {
            description: "a scope severity resolves to the scope enum",
            shape: ("sqlbuild.compiler.scopes.types", "DiagnosticSeverity"),
            expected_native: Some("ScopeDiagnosticSeverity"),
        },
        NativeNameTestCase {
            description: "a shape name from another module is not hosted",
            shape: ("sqlbuild.compiler.compile.models", "DiagnosticSeverity"),
            expected_native: None,
        },
        NativeNameTestCase {
            description: "a hosted planner record resolves by its own name",
            shape: ("sqlbuild.compiler.planner.models", "PlanOutput"),
            expected_native: Some("PlanOutput"),
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            hosted_native_name(test_case.shape.0, test_case.shape.1),
            Ok(test_case.expected_native),
            "{}",
            test_case.description
        );
    }
}
