use crate::semantic_validation::main::diagnostics::binding_diagnostics;
use crate::semantic_validation::tests::test_types::TypeLocationTestCase;

#[test]
fn given_position_less_type_findings_when_mapping_then_each_points_at_its_own_expression()
-> Result<(), String> {
    let test_cases = [
        TypeLocationTestCase {
            description: "two literal casts land on their own casts",
            sql: "SELECT CAST(TIMESTAMP '2026-04-01' AS INTEGER) AS a, \
                  CAST(TIMESTAMP '2026-04-02' AS INTEGER) AS b FROM orders",
            dialect: "duckdb",
            findings: &[
                ("W213", "Cannot cast timestamp to integer"),
                ("W213", "Cannot cast timestamp to integer"),
            ],
            expected_starts: &["CAST(TIMESTAMP '2026-04-01'", "CAST(TIMESTAMP '2026-04-02'"],
        },
        TypeLocationTestCase {
            description: "a literal cast skips an unrelated cast to the same type",
            sql: "SELECT CAST(1 AS INTEGER) AS a UNION ALL \
                  SELECT CAST(TIMESTAMP '2026-01-01' AS INTEGER)",
            dialect: "duckdb",
            findings: &[("E218", "Cannot cast timestamp to integer")],
            expected_starts: &["CAST(TIMESTAMP"],
        },
        TypeLocationTestCase {
            description: "set-operation findings point at the branch projection",
            sql: "SELECT 1 AS order_id, 'open' AS status UNION ALL SELECT 'x', 'closed' \
                  UNION ALL SELECT 'y', 'void'",
            dialect: "snowflake",
            findings: &[
                (
                    "W214",
                    "Set-operation column 1 may fail during runtime conversion: \
                     accumulated type NUMBER, next type VARCHAR",
                ),
                (
                    "W214",
                    "Set-operation column 1 may fail during runtime conversion: \
                     accumulated type NUMBER, next type VARCHAR",
                ),
            ],
            expected_starts: &["'x'", "'y'"],
        },
        TypeLocationTestCase {
            description: "coercible-literal comparisons land on their own literals",
            sql: "SELECT 1 = 'not-a-number' AS first_result, 2 = 'not-a-number' AS second_result",
            dialect: "duckdb",
            findings: &[
                ("W213", "Comparison contains an invalid coercible literal"),
                ("W213", "Comparison contains an invalid coercible literal"),
            ],
            expected_starts: &["'not-a-number' AS first", "'not-a-number' AS second"],
        },
        TypeLocationTestCase {
            description: "a set-operation arity finding points at the operator",
            sql: "SELECT 1 AS a, 2 AS b EXCEPT SELECT 1",
            dialect: "duckdb",
            findings: &[(
                "E216",
                "Set-operation operands return different column counts: left 2, right 1",
            )],
            expected_starts: &["EXCEPT"],
        },
    ];
    for test_case in &test_cases {
        let rows = test_case
            .findings
            .iter()
            .map(|(code, message)| {
                (
                    (*code).to_owned(),
                    (*message).to_owned(),
                    None,
                    None,
                    None,
                    None,
                    "error".to_owned(),
                )
            })
            .collect();
        let mapped = binding_diagnostics(test_case.sql, test_case.dialect, rows)?;
        let observed: Vec<String> = mapped
            .iter()
            .zip(test_case.expected_starts)
            .map(|(row, expected)| {
                row.4.map_or_else(String::new, |start| {
                    test_case
                        .sql
                        .chars()
                        .skip(start)
                        .take(expected.chars().count())
                        .collect()
                })
            })
            .collect();
        assert_eq!(
            mapped.len(),
            test_case.expected_starts.len(),
            "{}",
            test_case.description
        );
        assert_eq!(
            observed, test_case.expected_starts,
            "{}",
            test_case.description
        );
        assert!(
            mapped.iter().all(|row| row.2.is_some() && row.3.is_some()),
            "{}",
            test_case.description
        );
    }
    Ok(())
}
