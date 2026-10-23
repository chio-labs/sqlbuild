use crate::sql_macros::main::sql_macro_declared_outputs::sql_macro_declared_outputs;
use crate::sql_macros::main::sql_macro_declared_type::sql_macro_declared_type;
use crate::sql_macros::main::sql_macro_output_names::sql_macro_output_names;
use crate::sql_macros::models::CallScope;
use crate::sql_macros::tests::helpers::typed_check;
use crate::sql_macros::tests::test_types::{OutputNamesTestCase, OutputTypeTestCase};

#[test]
fn given_a_typed_macro_output_when_typing_the_column_then_returns_fills_unknown_and_refines() {
    let test_cases = [
        OutputTypeTestCase {
            description: "unknown inferred type takes returns",
            check: typed_check(CallScope::Main, true),
            item: (None, "label", None),
            expected_type: Some("VARCHAR"),
        },
        OutputTypeTestCase {
            description: "an identical type takes returns' spelling",
            check: typed_check(CallScope::Main, true),
            item: (None, "LABEL", Some("TEXT")),
            expected_type: Some("VARCHAR"),
        },
        OutputTypeTestCase {
            description: "a different known family keeps the inferred type",
            check: typed_check(CallScope::Main, true),
            item: (None, "label", Some("BIGINT")),
            expected_type: None,
        },
        OutputTypeTestCase {
            description: "a longer text type stays",
            check: typed_check(CallScope::Main, true),
            item: (None, "label", Some("VARCHAR(100)")),
            expected_type: None,
        },
        OutputTypeTestCase {
            description: "a known time type is not unknown",
            check: typed_check(CallScope::Main, true),
            item: (None, "label", Some("TIME")),
            expected_type: None,
        },
        OutputTypeTestCase {
            description: "a known array type is not unknown",
            check: typed_check(CallScope::Main, true),
            item: (None, "label", Some("TEXT[]")),
            expected_type: None,
        },
        OutputTypeTestCase {
            description: "another column is untouched",
            check: typed_check(CallScope::Main, true),
            item: (None, "other", None),
            expected_type: None,
        },
        OutputTypeTestCase {
            description: "a call in a CTE types that CTE's item",
            check: typed_check(CallScope::Cte("base".to_owned()), true),
            item: (Some("BASE"), "label", None),
            expected_type: Some("VARCHAR"),
        },
        OutputTypeTestCase {
            description: "a call in a CTE leaves a main-query item of that name",
            check: typed_check(CallScope::Cte("base".to_owned()), true),
            item: (None, "label", None),
            expected_type: None,
        },
        OutputTypeTestCase {
            description: "a call in a set operation is not typed",
            check: typed_check(CallScope::Main, false),
            item: (None, "label", None),
            expected_type: None,
        },
    ];

    for test_case in test_cases {
        let (cte, name, inferred) = test_case.item;
        let declared = sql_macro_declared_outputs(&[test_case.check]);
        let typed = sql_macro_declared_type(&declared, (cte, name), inferred, "duckdb");

        assert_eq!(
            typed.as_deref(),
            test_case.expected_type,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_model_sql_when_reading_sql_macro_outputs_then_only_whole_aliased_items_count() {
    let test_cases = [
        OutputNamesTestCase {
            description: "aliased whole items, with and without AS",
            sql: "SELECT @sql.a(x) AS one, @sql.b(y) two, @sql.c(z) AS \"Three\" FROM t",
            expected_names: &[(None, "one"), (None, "two"), (None, "Three")],
        },
        OutputNamesTestCase {
            description: "calls inside expressions or without an alias",
            sql: "SELECT @sql.a(x) || 'x' AS one, UPPER(@sql.b(y)) AS two, @sql.c(z) FROM t",
            expected_names: &[],
        },
        OutputNamesTestCase {
            description: "a call in a CTE, and one in a set operation",
            sql: "WITH c AS (SELECT @sql.a(x) AS one FROM t) SELECT @sql.b(y) AS two FROM c UNION ALL SELECT 'x' FROM c",
            expected_names: &[(Some("c"), "one")],
        },
        OutputNamesTestCase {
            description: "a call in the main query after CTEs",
            sql: "WITH c AS (SELECT x FROM t) SELECT x, @sql.a(x) AS one FROM c",
            expected_names: &[(None, "one")],
        },
    ];

    for test_case in test_cases {
        let names: Vec<(Option<String>, String)> = sql_macro_output_names(test_case.sql);
        let found: Vec<(Option<&str>, &str)> = names
            .iter()
            .map(|(cte, name)| (cte.as_deref(), name.as_str()))
            .collect();

        assert_eq!(found, test_case.expected_names, "{}", test_case.description);
    }
}
