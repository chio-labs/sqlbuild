use sqlbuild_sqltext::sql_scan::models::LexicalSyntax;

use crate::compiler::main::scenario_helper_scope::scenario_helper_scope;
use crate::compiler::main::scenario_reader_sql::scenario_reader_sql;
use crate::compiler::models::ScenarioScopeInput;
use crate::compiler::tests::test_types::ScenarioHelperScopeTestCase;

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
