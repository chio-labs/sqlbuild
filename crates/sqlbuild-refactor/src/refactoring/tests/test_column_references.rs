use crate::refactoring::errors::RefactorError;
use crate::refactoring::tests::helpers::plan_consumer;
use crate::refactoring::tests::test_types::ColumnEditTestCase;

#[test]
fn given_consumer_sql_when_planning_column_rename_then_edits_match() -> Result<(), RefactorError> {
    let test_cases = [
        ColumnEditTestCase {
            description: "bare projection keeps its output name",
            sql: "SELECT o.amount FROM __ref(\"fact_orders\") AS o",
            cascade: false,
            expected_sql: "SELECT o.revenue AS amount FROM __ref(\"fact_orders\") AS o",
            expected_passes_through: false,
            expected_manual: None,
        },
        ColumnEditTestCase {
            description: "cascade renames a bare projection's output",
            sql: "SELECT o.amount FROM __ref(\"fact_orders\") AS o",
            cascade: true,
            expected_sql: "SELECT o.revenue FROM __ref(\"fact_orders\") AS o",
            expected_passes_through: true,
            expected_manual: None,
        },
        ColumnEditTestCase {
            description: "aliased projection keeps its alias",
            sql: "SELECT o.amount AS total FROM __ref(\"fact_orders\") AS o",
            cascade: true,
            expected_sql: "SELECT o.revenue AS total FROM __ref(\"fact_orders\") AS o",
            expected_passes_through: false,
            expected_manual: None,
        },
        ColumnEditTestCase {
            description: "filter reference is renamed",
            sql: "SELECT order_id FROM __ref(\"fact_orders\") WHERE amount > 0",
            cascade: false,
            expected_sql: "SELECT order_id FROM __ref(\"fact_orders\") WHERE revenue > 0",
            expected_passes_through: false,
            expected_manual: None,
        },
        ColumnEditTestCase {
            description: "same-named column of another relation is untouched",
            sql: "SELECT c.amount FROM __ref(\"fact_orders\") AS o JOIN __ref(\"customers\") AS c ON o.customer_id = c.customer_id",
            cascade: false,
            expected_sql: "SELECT c.amount FROM __ref(\"fact_orders\") AS o JOIN __ref(\"customers\") AS c ON o.customer_id = c.customer_id",
            expected_passes_through: false,
            expected_manual: None,
        },
        ColumnEditTestCase {
            description: "star through a CTE is followed",
            sql: "WITH c AS (SELECT * FROM __ref(\"fact_orders\")) SELECT c.amount FROM c",
            cascade: false,
            expected_sql: "WITH c AS (SELECT * FROM __ref(\"fact_orders\")) SELECT c.revenue AS amount FROM c",
            expected_passes_through: false,
            expected_manual: None,
        },
        ColumnEditTestCase {
            description: "root star needs cascade",
            sql: "SELECT * FROM __ref(\"fact_orders\")",
            cascade: false,
            expected_sql: "SELECT * FROM __ref(\"fact_orders\")",
            expected_passes_through: false,
            expected_manual: Some("rerun with --cascade"),
        },
        ColumnEditTestCase {
            description: "root star passes through under cascade",
            sql: "SELECT * FROM __ref(\"fact_orders\")",
            cascade: true,
            expected_sql: "SELECT * FROM __ref(\"fact_orders\")",
            expected_passes_through: true,
            expected_manual: None,
        },
        ColumnEditTestCase {
            description: "USING join is left for the author",
            sql: "SELECT o.order_id FROM __ref(\"fact_orders\") AS o JOIN __ref(\"customers\") AS c USING (amount)",
            cascade: false,
            expected_sql: "SELECT o.order_id FROM __ref(\"fact_orders\") AS o JOIN __ref(\"customers\") AS c USING (amount)",
            expected_passes_through: false,
            expected_manual: Some("USING or NATURAL join"),
        },
    ];
    for test_case in test_cases {
        let (sql, passes_through, reasons) = plan_consumer(test_case.sql, test_case.cascade)?;
        let fragment: &str = test_case.expected_manual.unwrap_or_default();
        assert_eq!(
            (
                sql.as_str(),
                passes_through,
                !reasons.is_empty(),
                reasons.iter().all(|reason| reason.contains(fragment)),
            ),
            (
                test_case.expected_sql,
                test_case.expected_passes_through,
                test_case.expected_manual.is_some(),
                true,
            ),
            "{}",
            test_case.description
        );
    }
    Ok(())
}
