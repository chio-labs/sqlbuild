use crate::stage_capture::constants::HOSTED_SHAPE_TYPES;
use crate::stage_capture::tests::helpers::duplicates;
use crate::stage_capture::tests::test_types::HostedKeyTestCase;

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
