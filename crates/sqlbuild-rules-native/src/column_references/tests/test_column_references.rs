use crate::column_references::tests::helpers::{analyze, count, slices, strings};
use crate::column_references::tests::test_types::ColumnReferenceTestCase;
use serde_json::Value;

#[test]
fn given_column_uses_when_analyzing_then_reports_rename_sites() -> Result<(), String> {
    let test_cases = [
        ColumnReferenceTestCase {
            description: "qualified and unqualified uses across clauses",
            sql: "SELECT f.amount, SUM(amount) AS total FROM orders_fact f \
                  JOIN customers c ON c.order_id = f.order_id WHERE amount > 0 GROUP BY f.amount",
            output_ctes: &[],
            expected_parsed: true,
            expected_names: &["amount", "amount", "amount", "amount"],
            expected_scopes: &["root", "root", "root", "root"],
            expected_bare_projections: 1,
            expected_aliases: &[],
            expected_star_scopes: &[],
            expected_joins: 0,
            expected_output_aliases: &[],
            expected_outputs: 0,
        },
        ColumnReferenceTestCase {
            description: "same-named column of another relation is not the target",
            sql: "SELECT c.amount FROM customers c JOIN orders_fact f ON c.order_id = f.order_id",
            output_ctes: &[],
            expected_parsed: true,
            expected_names: &[],
            expected_scopes: &[],
            expected_bare_projections: 0,
            expected_aliases: &[],
            expected_star_scopes: &[],
            expected_joins: 0,
            expected_output_aliases: &[],
            expected_outputs: 0,
        },
        ColumnReferenceTestCase {
            description: "pass-through inside a CTE is reported in the CTE scope",
            sql: "WITH x AS (SELECT amount FROM orders_fact) SELECT amount FROM x",
            output_ctes: &[],
            expected_parsed: true,
            expected_names: &["amount"],
            expected_scopes: &["cte:x"],
            expected_bare_projections: 1,
            expected_aliases: &[],
            expected_star_scopes: &[],
            expected_joins: 0,
            expected_output_aliases: &[],
            expected_outputs: 0,
        },
        ColumnReferenceTestCase {
            description: "a star CTE over the target makes its column a target too",
            sql: "WITH x AS (SELECT * FROM orders_fact) SELECT x.amount AS a FROM x",
            output_ctes: &[],
            expected_parsed: true,
            expected_names: &["amount"],
            expected_scopes: &["root"],
            expected_bare_projections: 0,
            expected_aliases: &["a"],
            expected_star_scopes: &["cte:x"],
            expected_joins: 0,
            expected_output_aliases: &[],
            expected_outputs: 0,
        },
        ColumnReferenceTestCase {
            description: "a USING join on the column is reported",
            sql: "SELECT order_id FROM orders_fact JOIN customers USING (amount)",
            output_ctes: &[],
            expected_parsed: true,
            expected_names: &[],
            expected_scopes: &[],
            expected_bare_projections: 0,
            expected_aliases: &[],
            expected_star_scopes: &[],
            expected_joins: 1,
            expected_output_aliases: &[],
            expected_outputs: 0,
        },
        ColumnReferenceTestCase {
            description: "output scopes report aliased and bare projections of every branch",
            sql: "WITH fixture AS (SELECT 1 AS amount UNION ALL SELECT 2 AS amount) \
                  SELECT amount FROM orders_fact",
            output_ctes: &["fixture", "root"],
            expected_parsed: true,
            expected_names: &["amount"],
            expected_scopes: &["root"],
            expected_bare_projections: 1,
            expected_aliases: &[],
            expected_star_scopes: &[],
            expected_joins: 0,
            expected_output_aliases: &["amount", "amount"],
            expected_outputs: 3,
        },
        ColumnReferenceTestCase {
            description: "a later set-operation branch does not name the output",
            sql: "SELECT amount FROM customers UNION ALL SELECT amount FROM orders_fact",
            output_ctes: &[],
            expected_parsed: true,
            expected_names: &["amount"],
            expected_scopes: &["root"],
            expected_bare_projections: 0,
            expected_aliases: &[],
            expected_star_scopes: &[],
            expected_joins: 0,
            expected_output_aliases: &[],
            expected_outputs: 0,
        },
        ColumnReferenceTestCase {
            description: "the first branch of a nested set operation names the output",
            sql: "(SELECT amount FROM orders_fact EXCEPT SELECT amount FROM orders_fact) \
                  UNION ALL SELECT * FROM orders_fact",
            output_ctes: &[],
            expected_parsed: true,
            expected_names: &["amount", "amount"],
            expected_scopes: &["root", "root"],
            expected_bare_projections: 1,
            expected_aliases: &[],
            expected_star_scopes: &[],
            expected_joins: 0,
            expected_output_aliases: &[],
            expected_outputs: 0,
        },
        ColumnReferenceTestCase {
            description: "a star in a later branch does not pass the column through",
            sql: "WITH x AS (SELECT 1 AS order_id, 2 AS amount UNION ALL SELECT * FROM orders_fact) \
                  SELECT * FROM customers UNION ALL SELECT * FROM orders_fact",
            output_ctes: &[],
            expected_parsed: true,
            expected_names: &[],
            expected_scopes: &[],
            expected_bare_projections: 0,
            expected_aliases: &[],
            expected_star_scopes: &[],
            expected_joins: 0,
            expected_output_aliases: &[],
            expected_outputs: 0,
        },
        ColumnReferenceTestCase {
            description: "unparseable SQL reports that it was not analysed",
            sql: "SELECT FROM WHERE (",
            output_ctes: &[],
            expected_parsed: false,
            expected_names: &[],
            expected_scopes: &[],
            expected_bare_projections: 0,
            expected_aliases: &[],
            expected_star_scopes: &[],
            expected_joins: 0,
            expected_output_aliases: &[],
            expected_outputs: 0,
        },
    ];
    for test_case in &test_cases {
        let response: Value = analyze(test_case.sql, test_case.output_ctes)?;
        let references: &Value = &response["references"];
        let projections: Vec<&Value> = references
            .as_array()
            .map(|items| items.iter().map(|item| &item["projection"]).collect())
            .unwrap_or_default();
        let bare: usize = projections
            .iter()
            .filter(|projection| projection.is_object() && projection["alias"].is_null())
            .count();
        let aliases: Vec<String> = projections
            .iter()
            .filter_map(|projection| projection["alias"].as_str().map(str::to_string))
            .collect();
        assert_eq!(
            response["parsed"], test_case.expected_parsed,
            "{}",
            test_case.description
        );
        assert_eq!(
            slices(test_case.sql, references, "nameStart", "nameEnd"),
            test_case.expected_names,
            "{}",
            test_case.description
        );
        assert_eq!(
            strings(references, "scope"),
            test_case.expected_scopes,
            "{}",
            test_case.description
        );
        assert_eq!(
            bare, test_case.expected_bare_projections,
            "{}",
            test_case.description
        );
        assert_eq!(
            aliases, test_case.expected_aliases,
            "{}",
            test_case.description
        );
        assert_eq!(
            strings(&response["stars"], "scope"),
            test_case.expected_star_scopes,
            "{}",
            test_case.description
        );
        assert_eq!(
            count(&response["joins"]),
            test_case.expected_joins,
            "{}",
            test_case.description
        );
        assert_eq!(
            slices(
                test_case.sql,
                &response["outputs"],
                "aliasStart",
                "aliasEnd"
            ),
            test_case.expected_output_aliases,
            "{}",
            test_case.description
        );
        assert_eq!(
            count(&response["outputs"]),
            test_case.expected_outputs,
            "{}",
            test_case.description
        );
    }
    Ok(())
}
