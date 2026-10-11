use crate::sql_tests::main::sql_test_block::sql_test_block;
use crate::sql_tests::tests::test_types::SqlTestModeTestCase;

#[test]
fn given_test_bodies_when_inferring_mode_then_top_level_actual_ctes_decide() {
    let test_cases = [
        SqlTestModeTestCase {
            description: "plain SQL tests a model",
            sql_body: "SELECT 1",
            expected_mode: Ok("model"),
        },
        SqlTestModeTestCase {
            description: "a top-level macro actual CTE with a column list",
            sql_body: "WITH __macro_actual__ (a) AS (SELECT 1) SELECT 1",
            expected_mode: Ok("macro"),
        },
        SqlTestModeTestCase {
            description: "actual CTE names in strings, comments and subqueries are ignored",
            sql_body: "SELECT '__udf_actual__ AS', (WITH __udf_actual__ AS (SELECT 1) SELECT 1) \
                       -- __macro_actual__ AS",
            expected_mode: Ok("model"),
        },
        SqlTestModeTestCase {
            description: "two kinds of actual CTE are rejected",
            sql_body: "WITH __udf_actual__ AS (SELECT 1), __macro_actual__ AS (SELECT 2) SELECT 1",
            expected_mode: Err(
                "SQL test 't.sql' defines actual CTEs for several test modes (udf, macro); each \
                 TEST block tests one kind of logic",
            ),
        },
    ];

    for test_case in test_cases {
        let mode = sql_test_block(&[], test_case.sql_body, "t.sql").map(|block| block.mode);

        assert_eq!(
            mode,
            test_case.expected_mode.map_err(str::to_owned),
            "{}",
            test_case.description
        );
    }
}
