use sqlbuild_sqltext::sql_scan::models::LexicalSyntax;

use crate::compiler::main::scenario_helper_scope::scenario_helper_scope;
use crate::compiler::main::scenario_reader_sql::scenario_reader_sql;
use crate::compiler::models::ScenarioScopeInput;
use crate::compiler::tests::test_types::{
    ScenarioHelperScopeTestCase, ScenarioHelperShadowTestCase,
};

#[test]
fn given_scenario_helpers_when_scoping_a_reader_then_prepends_what_it_reads_in_order() {
    let ctes = [
        ("__ref__orders", "SELECT * FROM main.fixture_orders"),
        ("placed", "SELECT order_id FROM __ref__orders"),
        ("unused", "SELECT * FROM __ref(\"order_flags\")"),
        ("flagged", "SELECT order_id FROM placed"),
    ]
    .map(|(name, sql)| (name.to_owned(), sql.to_owned()));
    let scope = scenario_helper_scope(&ScenarioScopeInput {
        ctes: &ctes,
        checks: &[],
        lexical: LexicalSyntax::default(),
        dialect: Some("duckdb"),
        file_label: "tests/scenarios/orders.sql",
    })
    .expect("scope");
    let test_cases = [
        ScenarioHelperScopeTestCase {
            description: "chained helpers and the fixture they read come first",
            reader_sql: "SELECT * FROM flagged",
            fixtures: true,
            expected_sql: "WITH __ref__orders AS (SELECT * FROM main.fixture_orders), placed AS \
                           (SELECT order_id FROM __ref__orders), flagged AS (SELECT order_id \
                           FROM placed) SELECT * FROM flagged",
        },
        ScenarioHelperScopeTestCase {
            description: "a fixture reader gets helpers but not fixture stand-ins",
            reader_sql: "SELECT * FROM placed",
            fixtures: false,
            expected_sql: "WITH placed AS (SELECT order_id FROM __ref__orders) SELECT * FROM placed",
        },
        ScenarioHelperScopeTestCase {
            description: "a reader with its own WITH keeps it after the helpers",
            reader_sql: "WITH local AS (SELECT * FROM placed) SELECT * FROM local",
            fixtures: false,
            expected_sql: "WITH placed AS (SELECT order_id FROM __ref__orders), local AS \
                           (SELECT * FROM placed) SELECT * FROM local",
        },
        ScenarioHelperScopeTestCase {
            description: "a reader without helper reads is unchanged",
            reader_sql: "SELECT 1",
            fixtures: true,
            expected_sql: "SELECT 1",
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            scenario_reader_sql(&scope, test_case.reader_sql, test_case.fixtures),
            test_case.expected_sql,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_check_redefining_a_helper_name_when_scoping_then_rejects_like_sql_tests() {
    let ctes = [
        ("__ref__orders", "SELECT * FROM main.fixture_orders"),
        ("expected_rows", "SELECT 'o1' AS order_id"),
    ]
    .map(|(name, sql)| (name.to_owned(), sql.to_owned()));
    let test_cases = [
        ScenarioHelperShadowTestCase {
            description: "an assertion defining a helper's name inside its WITH",
            check_name: "__assert__flags_match",
            check_sql: "WITH expected_rows AS (SELECT 'o2' AS order_id) \
                        SELECT order_id FROM expected_rows",
            expected_rejected: true,
        },
        ScenarioHelperShadowTestCase {
            description: "an expected output defining a helper's name inside its WITH",
            check_name: "__expected__order_flags",
            check_sql: "WITH expected_rows AS (SELECT 'o2' AS order_id) \
                        SELECT order_id FROM expected_rows",
            expected_rejected: true,
        },
        ScenarioHelperShadowTestCase {
            description: "a check reading the helper without redefining it",
            check_name: "__assert__reads_only",
            check_sql: "SELECT order_id FROM expected_rows",
            expected_rejected: false,
        },
    ];
    for test_case in test_cases {
        let checks = [(
            test_case.check_name.to_owned(),
            test_case.check_sql.to_owned(),
        )];
        let rejected: bool = scenario_helper_scope(&ScenarioScopeInput {
            ctes: &ctes,
            checks: &checks,
            lexical: LexicalSyntax::default(),
            dialect: Some("duckdb"),
            file_label: "tests/scenarios/orders.sql",
        })
        .err()
        .is_some_and(|message| message.contains("redefines helper CTE 'expected_rows'"));
        assert_eq!(
            rejected, test_case.expected_rejected,
            "{}",
            test_case.description
        );
    }
}
