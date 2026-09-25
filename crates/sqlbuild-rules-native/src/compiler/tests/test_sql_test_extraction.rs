use crate::compiler::_helpers::sql_tests::extraction::{
    find_top_level_keyword, split_set_operations, split_top_level,
};
use crate::compiler::tests::helpers::{
    dependent_assertion_returns_authoritative_error,
    empty_model_fixture_marker_preserves_direct_mode_validation,
    expected_projection_errors_name_the_expected_cte,
    mixed_expanded_tests_preserve_order_and_payloads,
    quoted_ctes_and_implicit_alias_preserve_payload,
    set_operation_expected_ctes_validate_every_branch,
};
use crate::compiler::tests::test_types::{SqlTestExtractionTestCase, TopLevelScanTestCase};

#[test]
fn given_sql_test_cases_when_extracting_native_payloads_then_expected_behavior_holds() {
    let test_cases = [
        SqlTestExtractionTestCase {
            description: "mixed expanded tests preserve order and payloads",
            run: mixed_expanded_tests_preserve_order_and_payloads,
            expected_success: true,
        },
        SqlTestExtractionTestCase {
            description: "dependent assertions return the authoritative error",
            run: dependent_assertion_returns_authoritative_error,
            expected_success: true,
        },
        SqlTestExtractionTestCase {
            description: "quoted CTEs and implicit aliases preserve payloads",
            run: quoted_ctes_and_implicit_alias_preserve_payload,
            expected_success: true,
        },
        SqlTestExtractionTestCase {
            description: "empty model fixture marker preserves direct-mode validation",
            run: empty_model_fixture_marker_preserves_direct_mode_validation,
            expected_success: true,
        },
        SqlTestExtractionTestCase {
            description: "expected projection errors name the expected CTE",
            run: expected_projection_errors_name_the_expected_cte,
            expected_success: true,
        },
        SqlTestExtractionTestCase {
            description: "set-operation expected CTEs validate every branch",
            run: set_operation_expected_ctes_validate_every_branch,
            expected_success: true,
        },
    ];

    for test_case in test_cases {
        let actual_success = (test_case.run)();
        assert_eq!(
            actual_success, test_case.expected_success,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_expected_cte_sql_when_scanning_top_level_then_set_operations_commas_and_keywords_are_pinned()
 {
    let unclosed_quote = "SQL test contains an unclosed quoted string".to_owned();
    let unclosed_comment = "SQL test contains an unclosed block comment".to_owned();
    let test_cases = [
        TopLevelScanTestCase {
            description: "plain select",
            sql: "SELECT a, b AS c FROM orders",
            expected_unions: Ok(vec!["SELECT a, b AS c FROM orders"]),
            expected_commas: Ok(vec!["SELECT a", "b AS c FROM orders"]),
            expected_from: Ok(Some(17)),
        },
        TopLevelScanTestCase {
            description: "union quantifiers and comments between keywords",
            sql: "SELECT 1 AS a UNION ALL SELECT 2 AS a UNION /* x */ DISTINCT -- y\n SELECT 3 AS a UNION SELECT 4 AS a",
            expected_unions: Ok(vec![
                "SELECT 1 AS a",
                "SELECT 2 AS a",
                "SELECT 3 AS a",
                "SELECT 4 AS a",
            ]),
            expected_commas: Ok(vec![
                "SELECT 1 AS a UNION ALL SELECT 2 AS a UNION /* x */ DISTINCT -- y\n SELECT 3 AS a UNION SELECT 4 AS a",
            ]),
            expected_from: Ok(None),
        },
        TopLevelScanTestCase {
            description: "quotes comments and parentheses hide separators",
            sql: "SELECT 'x, UNION (' AS a, /* UNION , FROM */ \"b)\", `c,d`, f(1, (SELECT 2 FROM t UNION SELECT 3)) -- , FROM\nFROM t",
            expected_unions: Ok(vec![
                "SELECT 'x, UNION (' AS a, /* UNION , FROM */ \"b)\", `c,d`, f(1, (SELECT 2 FROM t UNION SELECT 3)) -- , FROM\nFROM t",
            ]),
            expected_commas: Ok(vec![
                "SELECT 'x, UNION (' AS a",
                "/* UNION , FROM */ \"b)\"",
                "`c,d`",
                "f(1, (SELECT 2 FROM t UNION SELECT 3)) -- , FROM\nFROM t",
            ]),
            expected_from: Ok(Some(107)),
        },
        TopLevelScanTestCase {
            description: "keyword boundaries and empty pieces",
            sql: ",SELECT reunion, union_id,, x FROMAGE UNION",
            expected_unions: Ok(vec![",SELECT reunion, union_id,, x FROMAGE"]),
            expected_commas: Ok(vec!["SELECT reunion", "union_id", "x FROMAGE UNION"]),
            expected_from: Ok(None),
        },
        TopLevelScanTestCase {
            description: "unbalanced close paren goes negative",
            sql: "SELECT a) UNION SELECT b, c FROM t",
            expected_unions: Ok(vec!["SELECT a) UNION SELECT b, c FROM t"]),
            expected_commas: Ok(vec!["SELECT a) UNION SELECT b, c FROM t"]),
            expected_from: Ok(None),
        },
        TopLevelScanTestCase {
            description: "multibyte text",
            sql: "SELECT 'é' AS ñ, ü FROM t UNION SELECT 1, 2",
            expected_unions: Ok(vec!["SELECT 'é' AS ñ, ü FROM t", "SELECT 1, 2"]),
            expected_commas: Ok(vec!["SELECT 'é' AS ñ", "ü FROM t UNION SELECT 1", "2"]),
            expected_from: Ok(Some(22)),
        },
        TopLevelScanTestCase {
            description: "intersect and except quantifiers mixed with union",
            sql: "SELECT 1 AS a INTERSECT ALL SELECT 2 AS a EXCEPT DISTINCT SELECT 3 AS a UNION SELECT 4 AS a EXCEPT SELECT 5 AS a",
            expected_unions: Ok(vec![
                "SELECT 1 AS a",
                "SELECT 2 AS a",
                "SELECT 3 AS a",
                "SELECT 4 AS a",
                "SELECT 5 AS a",
            ]),
            expected_commas: Ok(vec![
                "SELECT 1 AS a INTERSECT ALL SELECT 2 AS a EXCEPT DISTINCT SELECT 3 AS a UNION SELECT 4 AS a EXCEPT SELECT 5 AS a",
            ]),
            expected_from: Ok(None),
        },
        TopLevelScanTestCase {
            description: "star except modifier and identifier boundaries are not set operations",
            sql: "SELECT t.* EXCEPT (status), exceptional, intersection FROM t",
            expected_unions: Ok(vec![
                "SELECT t.* EXCEPT (status), exceptional, intersection FROM t",
            ]),
            expected_commas: Ok(vec![
                "SELECT t.* EXCEPT (status)",
                "exceptional",
                "intersection FROM t",
            ]),
            expected_from: Ok(Some(54)),
        },
        TopLevelScanTestCase {
            description: "unclosed quote",
            sql: "SELECT 'a, b FROM t",
            expected_unions: Err(unclosed_quote.clone()),
            expected_commas: Err(unclosed_quote.clone()),
            expected_from: Err(unclosed_quote),
        },
        TopLevelScanTestCase {
            description: "unclosed block comment after union",
            sql: "SELECT 1 UNION /* never closed",
            expected_unions: Err(unclosed_comment.clone()),
            expected_commas: Err(unclosed_comment.clone()),
            expected_from: Err(unclosed_comment),
        },
    ];
    for test_case in test_cases {
        assert_eq!(
            split_set_operations(test_case.sql),
            test_case.expected_unions,
            "unions: {}",
            test_case.description
        );
        assert_eq!(
            split_top_level(test_case.sql, b','),
            test_case.expected_commas,
            "commas: {}",
            test_case.description
        );
        assert_eq!(
            find_top_level_keyword(test_case.sql, 0, "FROM"),
            test_case.expected_from,
            "FROM: {}",
            test_case.description
        );
    }
}
