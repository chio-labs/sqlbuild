use crate::semantic_checks::_helpers::explanation::columns::{closest_column, ordered_columns};
use crate::semantic_checks::models::SemanticDeferral;
use crate::semantic_checks::tests::helpers::shape;
use crate::semantic_checks::tests::test_types::ClosestColumnTestCase;

const ORDER_COLUMNS: &[(&str, &str)] = &[
    ("order_id", "INTEGER"),
    ("customer_id", "INTEGER"),
    ("amount", "DOUBLE"),
    ("status", "VARCHAR"),
];

#[test]
fn given_unknown_column_names_when_suggesting_then_matches_python_order_and_choice() {
    let test_cases = [
        ClosestColumnTestCase {
            description: "a transposition within two edits",
            name: "amonut",
            columns: ORDER_COLUMNS,
            expected_closest: Ok(Some("amount")),
            expected_order: Ok(&["amount", "status", "customer_id", "order_id"]),
        },
        ClosestColumnTestCase {
            description: "an abbreviation keeping the first and last letters",
            name: "cust_id",
            columns: ORDER_COLUMNS,
            expected_closest: Ok(Some("customer_id")),
            expected_order: Ok(&["customer_id", "order_id", "status", "amount"]),
        },
        ClosestColumnTestCase {
            description: "a different case",
            name: "Amount",
            columns: ORDER_COLUMNS,
            expected_closest: Ok(Some("amount")),
            expected_order: Ok(&["amount", "customer_id", "order_id", "status"]),
        },
        ClosestColumnTestCase {
            description: "no close column",
            name: "zzz",
            columns: ORDER_COLUMNS,
            expected_closest: Ok(None),
            expected_order: Ok(&["amount", "customer_id", "order_id", "status"]),
        },
        ClosestColumnTestCase {
            description: "a column Python case-folds beyond ASCII",
            name: "strasse",
            columns: &[("stra\u{df}e", "VARCHAR")],
            expected_closest: Err(SemanticDeferral::NonAsciiText),
            expected_order: Err(SemanticDeferral::NonAsciiText),
        },
    ];
    for test_case in test_cases {
        let columns = shape(test_case.columns);
        assert_eq!(
            closest_column(test_case.name, &columns),
            test_case.expected_closest,
            "{}",
            test_case.description
        );
        assert_eq!(
            ordered_columns(test_case.name, &columns),
            test_case.expected_order.map(<[&str]>::to_vec),
            "{}",
            test_case.description
        );
    }
}
