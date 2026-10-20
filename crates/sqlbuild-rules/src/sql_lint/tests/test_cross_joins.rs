use crate::sql_lint::main::cross_join_subject::cross_join_subject;
use crate::sql_lint::tests::helpers::{
    POLICY_SENTINEL, cross_join_messages, cross_join_remediations,
};
use crate::sql_lint::tests::test_types::{CrossJoinSubjectTestCase, CrossJoinTestCase};

const GENERIC_MESSAGE: &str = "CROSS JOIN creates an explicit cartesian product";
const UNNAMED_MESSAGE: &str = "CROSS JOIN creates an explicit cartesian product with an unnamed relation; only a file-wide exception (rule and path) can cover it";

#[test]
fn given_cross_joins_when_one_side_is_provably_one_row_then_only_multiplying_joins_are_reported()
-> Result<(), String> {
    let test_cases = [
        CrossJoinTestCase {
            description: "two unknown relations multiply rows",
            sql: "SELECT o.order_id FROM orders AS o CROSS JOIN customers AS c",
            dialect: "duckdb",
            one_row_relations: &[],
            expected_messages: &[
                "CROSS JOIN with `customers` creates an explicit cartesian product",
            ],
        },
        CrossJoinTestCase {
            description: "a one-row seed on the right",
            sql: "SELECT o.order_id FROM orders AS o CROSS JOIN __sqb_lint_7__ AS p",
            dialect: "duckdb",
            one_row_relations: &[POLICY_SENTINEL],
            expected_messages: &[],
        },
        CrossJoinTestCase {
            description: "a seed with several rows names its relation",
            sql: "SELECT o.order_id FROM orders AS o CROSS JOIN __sqb_lint_7__ AS p",
            dialect: "duckdb",
            one_row_relations: &[],
            expected_messages: &[
                "CROSS JOIN with `order_policy` creates an explicit cartesian product",
            ],
        },
        CrossJoinTestCase {
            description: "a one-row seed on the left of the first join",
            sql: "SELECT o.order_id FROM __sqb_lint_7__ AS p CROSS JOIN orders AS o",
            dialect: "duckdb",
            one_row_relations: &[POLICY_SENTINEL],
            expected_messages: &[],
        },
        CrossJoinTestCase {
            description: "an aggregate without GROUP BY carried through a filtering CTE",
            sql: "WITH totals AS (SELECT COUNT(*) AS order_count FROM orders), \
                  kept AS (SELECT order_count FROM totals WHERE order_count > 0) \
                  SELECT o.order_id, k.order_count FROM orders AS o CROSS JOIN kept AS k",
            dialect: "duckdb",
            one_row_relations: &[],
            expected_messages: &[],
        },
        CrossJoinTestCase {
            description: "an aggregate with GROUP BY can return many rows",
            sql: "WITH totals AS (SELECT customer_id, COUNT(*) AS order_count FROM orders GROUP BY customer_id) \
                  SELECT o.order_id FROM orders AS o CROSS JOIN totals AS t",
            dialect: "duckdb",
            one_row_relations: &[],
            expected_messages: &["CROSS JOIN with `totals` creates an explicit cartesian product"],
        },
        CrossJoinTestCase {
            description: "a windowed count is not an aggregate",
            sql: "WITH totals AS (SELECT COUNT(*) OVER () AS order_count FROM orders) \
                  SELECT o.order_id FROM orders AS o CROSS JOIN totals AS t",
            dialect: "duckdb",
            one_row_relations: &[],
            expected_messages: &["CROSS JOIN with `totals` creates an explicit cartesian product"],
        },
        CrossJoinTestCase {
            description: "LIMIT 1",
            sql: "WITH latest AS (SELECT order_id FROM orders ORDER BY order_id DESC LIMIT 1) \
                  SELECT c.customer_id FROM customers AS c CROSS JOIN latest AS l",
            dialect: "duckdb",
            one_row_relations: &[],
            expected_messages: &[],
        },
        CrossJoinTestCase {
            description: "LIMIT 2 can return two rows",
            sql: "WITH latest AS (SELECT order_id FROM orders ORDER BY order_id DESC LIMIT 2) \
                  SELECT c.customer_id FROM customers AS c CROSS JOIN latest AS l",
            dialect: "duckdb",
            one_row_relations: &[],
            expected_messages: &["CROSS JOIN with `latest` creates an explicit cartesian product"],
        },
        CrossJoinTestCase {
            description: "one-row VALUES",
            sql: "WITH settings AS (SELECT * FROM (VALUES (1, 'EUR')) AS v(version, currency)) \
                  SELECT o.order_id FROM orders AS o CROSS JOIN settings AS s",
            dialect: "duckdb",
            one_row_relations: &[],
            expected_messages: &[],
        },
        CrossJoinTestCase {
            description: "two-row VALUES",
            sql: "WITH settings AS (SELECT * FROM (VALUES (1), (2)) AS v(version)) \
                  SELECT o.order_id FROM orders AS o CROSS JOIN settings AS s",
            dialect: "duckdb",
            one_row_relations: &[],
            expected_messages: &[
                "CROSS JOIN with `settings` creates an explicit cartesian product",
            ],
        },
        CrossJoinTestCase {
            description: "QUALIFY ROW_NUMBER() = 1 without a partition",
            sql: "WITH newest AS (SELECT order_id FROM orders QUALIFY ROW_NUMBER() OVER (ORDER BY order_id DESC) = 1) \
                  SELECT c.customer_id FROM customers AS c CROSS JOIN newest AS n",
            dialect: "snowflake",
            one_row_relations: &[],
            expected_messages: &[],
        },
        CrossJoinTestCase {
            description: "QUALIFY ROW_NUMBER() = 1 with a partition keeps one row per partition",
            sql: "WITH newest AS (SELECT order_id FROM orders QUALIFY ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY order_id DESC) = 1) \
                  SELECT c.customer_id FROM customers AS c CROSS JOIN newest AS n",
            dialect: "snowflake",
            one_row_relations: &[],
            expected_messages: &["CROSS JOIN with `newest` creates an explicit cartesian product"],
        },
        CrossJoinTestCase {
            description: "a join inside the carrying CTE stops the proof",
            sql: "WITH totals AS (SELECT COUNT(*) AS n FROM orders), \
                  joined AS (SELECT t.n FROM totals AS t INNER JOIN customers AS c ON c.n = t.n) \
                  SELECT o.order_id FROM orders AS o CROSS JOIN joined AS j",
            dialect: "duckdb",
            one_row_relations: &[],
            expected_messages: &["CROSS JOIN with `joined` creates an explicit cartesian product"],
        },
        CrossJoinTestCase {
            description: "UNNEST in a carrying CTE stops the proof",
            sql: "WITH totals AS (SELECT LIST(order_id) AS ids FROM orders), \
                  expanded AS (SELECT UNNEST(ids) AS order_id FROM totals) \
                  SELECT c.customer_id FROM customers AS c CROSS JOIN expanded AS e",
            dialect: "duckdb",
            one_row_relations: &[],
            expected_messages: &[
                "CROSS JOIN with `expanded` creates an explicit cartesian product",
            ],
        },
        CrossJoinTestCase {
            description: "a set operation stops the proof",
            sql: "WITH both_totals AS (SELECT COUNT(*) AS n FROM orders UNION ALL SELECT COUNT(*) AS n FROM customers) \
                  SELECT o.order_id FROM orders AS o CROSS JOIN both_totals AS b",
            dialect: "duckdb",
            one_row_relations: &[],
            expected_messages: &[
                "CROSS JOIN with `both_totals` creates an explicit cartesian product",
            ],
        },
        CrossJoinTestCase {
            description: "the finding names the CTE that contains the join",
            sql: "WITH checks AS (SELECT o.order_id FROM orders AS o CROSS JOIN customers AS c) \
                  SELECT order_id FROM checks",
            dialect: "duckdb",
            one_row_relations: &[],
            expected_messages: &[
                "CROSS JOIN with `customers` in CTE `checks` creates an explicit cartesian product",
            ],
        },
        CrossJoinTestCase {
            description: "a later join still multiplies the rows before it",
            sql: "SELECT o.order_id FROM __sqb_lint_7__ AS p CROSS JOIN orders AS o CROSS JOIN customers AS c",
            dialect: "duckdb",
            one_row_relations: &[POLICY_SENTINEL],
            expected_messages: &[
                "CROSS JOIN with `customers` creates an explicit cartesian product",
            ],
        },
        CrossJoinTestCase {
            description: "an unnamed relation says only a file-wide exception covers it",
            sql: "SELECT o.order_id FROM orders AS o CROSS JOIN UNNEST([1, 2]) AS u(n)",
            dialect: "duckdb",
            one_row_relations: &[],
            expected_messages: &[UNNAMED_MESSAGE],
        },
        CrossJoinTestCase {
            description: "a named window is never treated as unpartitioned",
            sql: "WITH newest AS (SELECT order_id FROM orders WINDOW w AS (PARTITION BY customer_id ORDER BY order_id DESC) QUALIFY ROW_NUMBER() OVER w = 1) \
                  SELECT c.customer_id FROM customers AS c CROSS JOIN newest AS n",
            dialect: "duckdb",
            one_row_relations: &[],
            expected_messages: &["CROSS JOIN with `newest` creates an explicit cartesian product"],
        },
        CrossJoinTestCase {
            description: "a join under a nested WITH names the top-level CTE",
            sql: "WITH outer_checks AS (WITH inner_checks AS (SELECT o.order_id FROM orders AS o CROSS JOIN customers AS c) SELECT order_id FROM inner_checks) \
                  SELECT order_id FROM outer_checks",
            dialect: "duckdb",
            one_row_relations: &[],
            expected_messages: &[
                "CROSS JOIN with `customers` in CTE `outer_checks` creates an explicit cartesian product",
            ],
        },
        CrossJoinTestCase {
            description: "a WITH inside a subquery of the final select names no CTE",
            sql: "SELECT s.order_id FROM (WITH inner_checks AS (SELECT o.order_id FROM orders AS o CROSS JOIN customers AS c) SELECT order_id FROM inner_checks) AS s",
            dialect: "duckdb",
            one_row_relations: &[],
            expected_messages: &[
                "CROSS JOIN with `customers` creates an explicit cartesian product",
            ],
        },
        CrossJoinTestCase {
            description: "a WITH owned by a set operation names its CTE",
            sql: "WITH checks AS (SELECT o.order_id FROM orders AS o CROSS JOIN customers AS c) \
                  SELECT order_id FROM checks UNION ALL SELECT order_id FROM orders",
            dialect: "duckdb",
            one_row_relations: &[],
            expected_messages: &[
                "CROSS JOIN with `customers` in CTE `checks` creates an explicit cartesian product",
            ],
        },
    ];

    for test_case in test_cases {
        let messages: Vec<String> = cross_join_messages(&test_case)?;

        assert_eq!(
            messages, test_case.expected_messages,
            "{}",
            test_case.description
        );
    }
    Ok(())
}

#[test]
fn given_unnamed_cross_join_when_linting_then_help_prints_a_file_wide_exception()
-> Result<(), String> {
    let test_cases = [CrossJoinTestCase {
        description: "CROSS JOIN UNNEST",
        sql: "SELECT o.order_id FROM orders AS o CROSS JOIN UNNEST([1, 2]) AS u(n)",
        dialect: "duckdb",
        one_row_relations: &[],
        expected_messages: &[
            "[[rules.rule_exceptions]]\n            rule = \"SQBRSQL038\"\n            path = \"<path of this file>\"\n            reason = \"<why this deviation is intentional>\"",
        ],
    }];

    for test_case in test_cases {
        let remediations: Vec<String> = cross_join_remediations(&test_case)?;

        assert_eq!(remediations.len(), 1, "{}", test_case.description);
        assert!(
            remediations[0].contains(test_case.expected_messages[0]),
            "{}: {remediations:?}",
            test_case.description
        );
    }
    Ok(())
}

#[test]
fn given_cross_join_messages_when_reading_their_subject_then_relation_and_cte_are_named() {
    let test_cases = [
        CrossJoinSubjectTestCase {
            description: "a top-level join",
            message: "CROSS JOIN with `order_policy` creates an explicit cartesian product",
            expected_subject: Some(("order_policy", None)),
        },
        CrossJoinSubjectTestCase {
            description: "a join inside a CTE",
            message: "CROSS JOIN with `order_policy` in CTE `order_checks` creates an explicit cartesian product",
            expected_subject: Some(("order_policy", Some("order_checks"))),
        },
        CrossJoinSubjectTestCase {
            description: "the generic message names nothing",
            message: GENERIC_MESSAGE,
            expected_subject: None,
        },
    ];

    for test_case in test_cases {
        let subject = cross_join_subject(test_case.message);

        assert_eq!(
            subject
                .as_ref()
                .map(|(relation, cte)| (relation.as_str(), cte.as_deref())),
            test_case.expected_subject,
            "{}",
            test_case.description
        );
    }
}
