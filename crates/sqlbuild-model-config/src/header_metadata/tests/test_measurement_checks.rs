use crate::header_metadata::main::check_measurement_contract::check_measurement_contract;
use crate::header_metadata::main::check_threshold_bound::check_threshold_bound;
use crate::header_metadata::models::{ThresholdBound, ThresholdInput};
use crate::header_metadata::tests::test_types::{
    MeasurementContractTestCase, ThresholdBoundTestCase,
};

#[test]
fn given_threshold_limits_when_checking_bound_then_matches_python_validation() {
    let test_cases = [
        ThresholdBoundTestCase {
            description: "a below limit becomes the bound",
            operator: "below",
            inputs: (
                ThresholdInput::Number(2.0),
                ThresholdInput::Absent,
                ThresholdInput::Absent,
            ),
            expected_bound: Ok(ThresholdBound::Below(2.0)),
        },
        ThresholdBoundTestCase {
            description: "a boolean limit is rejected after the shape check",
            operator: "above",
            inputs: (
                ThresholdInput::Boolean,
                ThresholdInput::Absent,
                ThresholdInput::Absent,
            ),
            expected_bound: Err("measurement threshold limit must not be boolean"),
        },
        ThresholdBoundTestCase {
            description: "a directional bound with a lower limit is rejected",
            operator: "above",
            inputs: (
                ThresholdInput::Number(1.0),
                ThresholdInput::Number(0.0),
                ThresholdInput::Absent,
            ),
            expected_bound: Err("above threshold requires limit only"),
        },
        ThresholdBoundTestCase {
            description: "an infinite limit is rejected",
            operator: "below",
            inputs: (
                ThresholdInput::Number(f64::INFINITY),
                ThresholdInput::Absent,
                ThresholdInput::Absent,
            ),
            expected_bound: Err("measurement threshold limit must be finite"),
        },
        ThresholdBoundTestCase {
            description: "an outside bound without an upper limit fails the shape check first",
            operator: "outside",
            inputs: (
                ThresholdInput::Absent,
                ThresholdInput::Boolean,
                ThresholdInput::Absent,
            ),
            expected_bound: Err("outside threshold requires lower and upper only"),
        },
        ThresholdBoundTestCase {
            description: "a boolean upper limit is rejected",
            operator: "outside",
            inputs: (
                ThresholdInput::Absent,
                ThresholdInput::Number(1.0),
                ThresholdInput::Boolean,
            ),
            expected_bound: Err("measurement threshold upper must not be boolean"),
        },
        ThresholdBoundTestCase {
            description: "a reversed outside range is rejected",
            operator: "outside",
            inputs: (
                ThresholdInput::Absent,
                ThresholdInput::Number(3.0),
                ThresholdInput::Number(1.0),
            ),
            expected_bound: Err("outside threshold lower must be less than or equal to upper"),
        },
        ThresholdBoundTestCase {
            description: "an outside range becomes the bound",
            operator: "outside",
            inputs: (
                ThresholdInput::Absent,
                ThresholdInput::Number(1.0),
                ThresholdInput::Number(3.0),
            ),
            expected_bound: Ok(ThresholdBound::Outside(1.0, 3.0)),
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            check_threshold_bound(test_case.operator, test_case.inputs),
            test_case.expected_bound.map_err(str::to_owned),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_contract_fields_when_checking_then_blank_names_are_rejected() {
    let test_cases = [
        MeasurementContractTestCase {
            description: "named columns are accepted",
            fields: ("value", Some("samples"), None),
            expected_result: Ok(()),
        },
        MeasurementContractTestCase {
            description: "a blank value column is rejected",
            fields: (" ", None, None),
            expected_result: Err("measurement contract value_column must be non-empty"),
        },
        MeasurementContractTestCase {
            description: "a blank sample unit is rejected",
            fields: ("value", None, Some("")),
            expected_result: Err("measurement contract sample_unit must be non-empty"),
        },
    ];
    for test_case in test_cases {
        let (value_column, sample_count_column, sample_unit) = test_case.fields;
        assert_eq!(
            check_measurement_contract(value_column, sample_count_column, sample_unit),
            test_case.expected_result,
            "{}",
            test_case.description
        );
    }
}
