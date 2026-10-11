use crate::sql_values::errors::SqlValueFailure;
use crate::sql_values::main::normalize_sql_value::normalize_sql_value;
use crate::sql_values::models::{RawSqlValue, SqlValueLimits};
use crate::sql_values::tests::helpers::integer_type;
use crate::sql_values::tests::test_types::NormalizeTestCase;
use sqlbuild_core::models::SqlValue;

#[test]
fn given_authored_values_when_normalizing_then_python_canonical_values_and_errors_match() {
    let test_cases = [
        NormalizeTestCase {
            description: "a set is deduplicated by identity and ordered by its repr",
            raw: RawSqlValue::Set(vec![RawSqlValue::Int(2), RawSqlValue::Int(10)]),
            explicit_type: None,
            expected_value: Ok(SqlValue::Set {
                element_type: integer_type(),
                values: vec![SqlValue::Integer(10), SqlValue::Integer(2)],
            }),
        },
        NormalizeTestCase {
            description: "a duplicate set value names its payload repr",
            raw: RawSqlValue::Set(vec![
                RawSqlValue::Str("GB".to_owned()),
                RawSqlValue::Str("GB".to_owned()),
            ]),
            explicit_type: None,
            expected_value: Err(SqlValueFailure::Invalid(
                "constant 'x' contains duplicate set value 'GB' at [1]".to_owned(),
            )),
        },
        NormalizeTestCase {
            description: "a quoted decimal keeps its exponent",
            raw: RawSqlValue::Str(" 2.4700 ".to_owned()),
            explicit_type: Some("decimal"),
            expected_value: Ok(SqlValue::Decimal("2.4700".to_owned())),
        },
        NormalizeTestCase {
            description: "a non-finite float is rejected with its repr",
            raw: RawSqlValue::Float(f64::INFINITY),
            explicit_type: None,
            expected_value: Err(SqlValueFailure::Invalid(
                "constant 'x' float must be finite; received inf".to_owned(),
            )),
        },
        NormalizeTestCase {
            description: "a set of decimals beyond Emax overflows like Decimal.normalize",
            raw: RawSqlValue::Set(vec![RawSqlValue::Decimal("1E+1000000".to_owned())]),
            explicit_type: None,
            expected_value: Err(SqlValueFailure::DecimalOverflow),
        },
    ];

    for test_case in test_cases {
        let normalized = normalize_sql_value(
            &test_case.raw,
            "constant 'x'",
            test_case.explicit_type,
            SqlValueLimits::default(),
        );

        assert_eq!(
            normalized, test_case.expected_value,
            "{}",
            test_case.description
        );
    }
}
