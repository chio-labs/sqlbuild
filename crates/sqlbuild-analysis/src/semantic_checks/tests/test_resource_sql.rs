use crate::semantic_checks::_helpers::resource_sql::fixtures::prepared_test_sql;
use crate::semantic_checks::tests::test_types::PreparedTestSqlTestCase;

#[test]
fn given_sql_test_bodies_when_preparing_then_empty_fixtures_open_as_python_rewrites_them() {
    let test_cases = [
        PreparedTestSqlTestCase {
            description: "an empty fixture CTE reads its own relation",
            sql_body: "WITH __ref__customers AS (SELECT * FROM __empty_fixture()) SELECT 1",
            expected_sql: "WITH __ref__customers AS (SELECT * FROM customers) SELECT 1",
            expected_relations: &["customers"],
        },
        PreparedTestSqlTestCase {
            description: "other empty fixtures open and reference calls are relations",
            sql_body: "SELECT * FROM __EMPTY_FIXTURE ( ) JOIN __ref('orders') AS o ON TRUE",
            expected_sql: "SELECT * FROM __sqlbuild_empty_fixture JOIN __ref('orders') AS o ON TRUE",
            expected_relations: &["orders"],
        },
        PreparedTestSqlTestCase {
            description: "a fixture name inside a longer word is not a CTE",
            sql_body: "WITH x__ref__a AS (SELECT * FROM __empty_fixture()) SELECT 1",
            expected_sql: "WITH x__ref__a AS (SELECT * FROM __sqlbuild_empty_fixture) SELECT 1",
            expected_relations: &[],
        },
    ];

    for test_case in test_cases {
        let (sql, relations) = prepared_test_sql(test_case.sql_body);

        assert_eq!(
            (
                sql.as_str(),
                relations.iter().map(String::as_str).collect::<Vec<_>>()
            ),
            (
                test_case.expected_sql,
                test_case.expected_relations.to_vec()
            ),
            "{}",
            test_case.description
        );
    }
}
