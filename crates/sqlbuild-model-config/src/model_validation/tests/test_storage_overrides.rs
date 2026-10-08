use crate::model_validation::main::retention_override::retention_override;
use crate::model_validation::main::table_type_override::table_type_override;
use crate::model_validation::models::{RetentionOverride, TableTypeOverride};
use crate::model_validation::tests::helpers::validator_error;
use crate::model_validation::tests::test_types::{
    RetentionOverrideTestCase, TableTypeOverrideTestCase,
};
use crate::tests::test_types::Value;

#[test]
fn given_header_retention_values_when_reading_then_python_policies_result() {
    let test_cases = [
        RetentionOverrideTestCase {
            description: "absent",
            value: None,
            expected_override: Ok(RetentionOverride::Inherit),
        },
        RetentionOverrideTestCase {
            description: "inherit",
            value: Some(Value::Str("inherit")),
            expected_override: Ok(RetentionOverride::Inherit),
        },
        RetentionOverrideTestCase {
            description: "disabled",
            value: Some(Value::Str("disabled")),
            expected_override: Ok(RetentionOverride::Unmanaged),
        },
        RetentionOverrideTestCase {
            description: "zero days",
            value: Some(Value::Str("0d")),
            expected_override: Ok(RetentionOverride::Days(0)),
        },
        RetentionOverrideTestCase {
            description: "whole days",
            value: Some(Value::Str("7d")),
            expected_override: Ok(RetentionOverride::Days(7)),
        },
        RetentionOverrideTestCase {
            description: "hours are not whole days",
            value: Some(Value::Str("1d6h")),
            expected_override: Err(validator_error(
                "time_travel_retention must be a whole-day string like '7d', 'inherit', or \
                 'disabled'",
            )),
        },
        RetentionOverrideTestCase {
            description: "not a string",
            value: Some(Value::Int(7)),
            expected_override: Err(validator_error(
                "time_travel_retention must be a whole-day string like '7d'",
            )),
        },
    ];

    for test_case in test_cases {
        let resolved = retention_override(test_case.value.as_ref(), "orders_daily");

        assert_eq!(
            resolved, test_case.expected_override,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_header_table_types_when_reading_then_python_types_result() {
    let test_cases = [
        TableTypeOverrideTestCase {
            description: "absent",
            value: None,
            expected_override: Ok(TableTypeOverride::Inherit),
        },
        TableTypeOverrideTestCase {
            description: "inherit",
            value: Some(Value::Str("inherit")),
            expected_override: Ok(TableTypeOverride::Inherit),
        },
        TableTypeOverrideTestCase {
            description: "permanent",
            value: Some(Value::Str("permanent")),
            expected_override: Ok(TableTypeOverride::Permanent),
        },
        TableTypeOverrideTestCase {
            description: "transient",
            value: Some(Value::Str("transient")),
            expected_override: Ok(TableTypeOverride::Transient),
        },
        TableTypeOverrideTestCase {
            description: "unknown",
            value: Some(Value::Str("temporary")),
            expected_override: Err(validator_error(
                "table_type must be permanent, transient, or inherit",
            )),
        },
    ];

    for test_case in test_cases {
        let resolved = table_type_override(test_case.value.as_ref(), "orders_daily");

        assert_eq!(
            resolved, test_case.expected_override,
            "{}",
            test_case.description
        );
    }
}
