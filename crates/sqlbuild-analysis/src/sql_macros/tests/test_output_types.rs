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
            check: typed_check(CallScope::Main, 0),
            item: (None, 0, "label", None),
            expected_type: Some("VARCHAR"),
        },
        OutputTypeTestCase {
            description: "an identical type takes returns' spelling",
            check: typed_check(CallScope::Main, 0),
            item: (None, 0, "LABEL", Some("TEXT")),
            expected_type: Some("VARCHAR"),
        },
        OutputTypeTestCase {
            description: "a different known family keeps the inferred type",
            check: typed_check(CallScope::Main, 0),
            item: (None, 0, "label", Some("BIGINT")),
            expected_type: None,
        },
        OutputTypeTestCase {
            description: "a longer text type stays",
            check: typed_check(CallScope::Main, 0),
            item: (None, 0, "label", Some("VARCHAR(100)")),
            expected_type: None,
        },
        OutputTypeTestCase {
            description: "the unknown placeholder takes returns",
            check: typed_check(CallScope::Main, 0),
            item: (None, 0, "label", Some("UNKNOWN")),
            expected_type: Some("VARCHAR"),
        },
        OutputTypeTestCase {
            description: "a known time type is not unknown",
            check: typed_check(CallScope::Main, 0),
            item: (None, 0, "label", Some("TIME")),
            expected_type: None,
        },
        OutputTypeTestCase {
            description: "a known array type is not unknown",
            check: typed_check(CallScope::Main, 0),
            item: (None, 0, "label", Some("TEXT[]")),
            expected_type: None,
        },
        OutputTypeTestCase {
            description: "another column is untouched",
            check: typed_check(CallScope::Main, 0),
            item: (None, 0, "other", None),
            expected_type: None,
        },
        OutputTypeTestCase {
            description: "a call in a CTE types that CTE's item",
            check: typed_check(CallScope::Cte("base".to_owned()), 0),
            item: (Some("BASE"), 0, "label", None),
            expected_type: Some("VARCHAR"),
        },
        OutputTypeTestCase {
            description: "a call in a CTE leaves a main-query item of that name",
            check: typed_check(CallScope::Cte("base".to_owned()), 0),
            item: (None, 0, "label", None),
            expected_type: None,
        },
        OutputTypeTestCase {
            description: "a call in another branch of a set operation leaves this one",
            check: typed_check(CallScope::Main, 1),
            item: (None, 0, "label", None),
            expected_type: None,
        },
        OutputTypeTestCase {
            description: "a call in a later branch of a set operation types that branch",
            check: typed_check(CallScope::Cte("base".to_owned()), 1),
            item: (Some("base"), 1, "label", Some("TEXT")),
            expected_type: Some("VARCHAR"),
        },
    ];

    for test_case in test_cases {
        let (cte, branch, name, inferred) = test_case.item;
        let declared = sql_macro_declared_outputs(&[test_case.check]);
        let typed = sql_macro_declared_type(&declared, (cte, branch, name), inferred, "duckdb");

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
            expected_names: &[(None, 0, "one"), (None, 0, "two"), (None, 0, "Three")],
        },
        OutputNamesTestCase {
            description: "calls inside expressions or without an alias",
            sql: "SELECT @sql.a(x) || 'x' AS one, UPPER(@sql.b(y)) AS two, @sql.c(z) FROM t",
            expected_names: &[],
        },
        OutputNamesTestCase {
            description: "a call in a CTE, and ones in each branch of a set operation",
            sql: "WITH c AS (SELECT @sql.a(x) AS one FROM t) SELECT @sql.b(y) AS two FROM c UNION ALL SELECT 'x' FROM c UNION ALL SELECT @sql.c(z) AS three FROM c",
            expected_names: &[(Some("c"), 0, "one"), (None, 0, "two"), (None, 2, "three")],
        },
        OutputNamesTestCase {
            description: "a star EXCEPT modifier is not a set operation",
            sql: "SELECT * EXCEPT (a) FROM t UNION ALL SELECT @sql.b(y) AS two FROM t",
            expected_names: &[(None, 1, "two")],
        },
        OutputNamesTestCase {
            description: "calls in subqueries, a nested WITH or beside a parenthesised branch",
            sql: "WITH c AS (WITH d AS (SELECT 1 AS x) SELECT @sql.a(x) AS one FROM d), e AS (SELECT * FROM (SELECT @sql.b(y) AS two FROM t) AS s) SELECT @sql.c(z) AS three FROM c UNION ALL (SELECT 'x' FROM e)",
            expected_names: &[],
        },
        OutputNamesTestCase {
            description: "a call in the main query after CTEs",
            sql: "WITH c AS (SELECT x FROM t) SELECT x, @sql.a(x) AS one FROM c",
            expected_names: &[(None, 0, "one")],
        },
    ];

    for test_case in test_cases {
        let names: Vec<(Option<String>, usize, String)> = sql_macro_output_names(test_case.sql);
        let found: Vec<(Option<&str>, usize, &str)> = names
            .iter()
            .map(|(cte, branch, name)| (cte.as_deref(), *branch, name.as_str()))
            .collect();

        assert_eq!(found, test_case.expected_names, "{}", test_case.description);
    }
}
