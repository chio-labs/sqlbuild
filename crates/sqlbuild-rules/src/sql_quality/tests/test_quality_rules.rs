use serde_json::Value;

use crate::sql_quality::tests::helpers::{anchors, fixed, lint};
use crate::sql_quality::tests::test_types::{QualityRemediationTestCase, QualityRuleTestCase};

#[test]
fn given_quality_rule_inputs_when_linting_then_findings_and_fixes_match() -> Result<(), String> {
    let test_cases = [
        QualityRuleTestCase {
            description: "long literal is reported without a split fix",
            sql: "SELECT 'pending orders awaiting shipment' AS label",
            rule: "SQBRSQL044",
            relation_keys: "{}",
            expected_anchors: &["'pending orders awaiting shipment'"],
            expected_fixed_sql: None,
        },
        QualityRuleTestCase {
            description: "short literal passes",
            sql: "SELECT 'pending' AS label",
            rule: "SQBRSQL044",
            relation_keys: "{}",
            expected_anchors: &[],
            expected_fixed_sql: None,
        },
        QualityRuleTestCase {
            description: "typed literal is reported without a fix",
            sql: "SELECT TIMESTAMP '2026-04-01 10:00:00.000000000' AS ordered_at",
            rule: "SQBRSQL044",
            relation_keys: "{}",
            expected_anchors: &["'2026-04-01 10:00:00.000000000'"],
            expected_fixed_sql: None,
        },
        QualityRuleTestCase {
            description: "ranking sort above the cap",
            sql: "SELECT ROW_NUMBER() OVER (PARTITION BY o.customer_id ORDER BY o.a, o.b, o.order_id) AS rn FROM orders AS o",
            rule: "SQBRSQL043",
            relation_keys: "{}",
            expected_anchors: &["ROW_NUMBER"],
            expected_fixed_sql: None,
        },
        QualityRuleTestCase {
            description: "ranking sort within the cap",
            sql: "SELECT RANK() OVER (ORDER BY o.a, o.order_id) AS rn FROM orders AS o",
            rule: "SQBRSQL043",
            relation_keys: "{}",
            expected_anchors: &[],
            expected_fixed_sql: None,
        },
        QualityRuleTestCase {
            description: "ordering covers a declared key",
            sql: "SELECT ROW_NUMBER() OVER (PARTITION BY o.customer_id ORDER BY o.ordered_at, o.order_id) AS rn FROM orders AS o",
            rule: "SQBRSQL018",
            relation_keys: r#"{"orders": [["order_id"]]}"#,
            expected_anchors: &[],
            expected_fixed_sql: None,
        },
        QualityRuleTestCase {
            description: "ordering without a key is unproven",
            sql: "SELECT ROW_NUMBER() OVER (PARTITION BY o.customer_id ORDER BY o.ordered_at) AS rn FROM orders AS o",
            rule: "SQBRSQL018",
            relation_keys: r#"{"orders": [["order_id"]]}"#,
            expected_anchors: &["ROW_NUMBER"],
            expected_fixed_sql: None,
        },
        QualityRuleTestCase {
            description: "key proven through a CTE and a one-to-one join",
            sql: "WITH lines AS (SELECT l.line_id, l.order_id FROM order_lines AS l), final AS (SELECT l.line_id, o.customer_id, ROW_NUMBER() OVER (PARTITION BY o.customer_id ORDER BY l.line_id) AS rn FROM lines AS l INNER JOIN orders AS o ON l.order_id = o.order_id) SELECT f.line_id, f.customer_id, f.rn FROM final AS f",
            rule: "SQBRSQL018",
            relation_keys: r#"{"orders": [["order_id"]], "order_lines": [["line_id"]]}"#,
            expected_anchors: &[],
            expected_fixed_sql: None,
        },
        QualityRuleTestCase {
            description: "key lost through a fan-out join",
            sql: "WITH final AS (SELECT o.order_id, ROW_NUMBER() OVER (ORDER BY o.order_id) AS rn FROM orders AS o INNER JOIN order_lines AS l ON l.order_id = o.order_id) SELECT f.order_id, f.rn FROM final AS f",
            rule: "SQBRSQL018",
            relation_keys: r#"{"orders": [["order_id"]], "order_lines": [["line_id"]]}"#,
            expected_anchors: &["ROW_NUMBER"],
            expected_fixed_sql: None,
        },
        QualityRuleTestCase {
            description: "GROUP BY grain is a key",
            sql: "WITH totals AS (SELECT o.customer_id, SUM(o.amount) AS amount FROM orders AS o GROUP BY o.customer_id), final AS (SELECT t.customer_id, ROW_NUMBER() OVER (ORDER BY t.amount, t.customer_id) AS rn FROM totals AS t) SELECT f.customer_id, f.rn FROM final AS f",
            rule: "SQBRSQL018",
            relation_keys: "{}",
            expected_anchors: &[],
            expected_fixed_sql: None,
        },
        QualityRuleTestCase {
            description: "positional GROUP BY grain is a key",
            sql: "WITH totals AS (SELECT o.customer_id, SUM(o.amount) AS amount FROM orders AS o GROUP BY 1), final AS (SELECT t.customer_id, ROW_NUMBER() OVER (ORDER BY t.amount, t.customer_id) AS rn FROM totals AS t) SELECT f.customer_id, f.rn FROM final AS f",
            rule: "SQBRSQL018",
            relation_keys: "{}",
            expected_anchors: &[],
            expected_fixed_sql: None,
        },
        QualityRuleTestCase {
            description: "a later rn = 1 filter makes the partition a key",
            sql: "WITH ranked AS (SELECT o.order_id, o.customer_id, ROW_NUMBER() OVER (PARTITION BY o.customer_id ORDER BY o.order_id) AS rn FROM orders AS o), latest AS (SELECT r.customer_id, r.order_id FROM ranked AS r WHERE r.rn = 1), final AS (SELECT l.customer_id, ROW_NUMBER() OVER (ORDER BY l.customer_id) AS position FROM latest AS l) SELECT f.customer_id, f.position FROM final AS f",
            rule: "SQBRSQL018",
            relation_keys: r#"{"orders": [["order_id"]]}"#,
            expected_anchors: &[],
            expected_fixed_sql: None,
        },
        QualityRuleTestCase {
            description: "a QUALIFY window cannot prove itself",
            sql: "SELECT o.customer_id, o.order_id FROM orders AS o QUALIFY ROW_NUMBER() OVER (PARTITION BY o.customer_id ORDER BY o.amount DESC) = 1",
            rule: "SQBRSQL018",
            relation_keys: r#"{"orders": [["order_id"]]}"#,
            expected_anchors: &["ROW_NUMBER"],
            expected_fixed_sql: None,
        },
        QualityRuleTestCase {
            description: "a QUALIFY partition is a key for later steps",
            sql: "WITH latest AS (SELECT o.customer_id, o.order_id FROM orders AS o QUALIFY ROW_NUMBER() OVER (PARTITION BY o.customer_id ORDER BY o.order_id) = 1), final AS (SELECT l.customer_id, ROW_NUMBER() OVER (ORDER BY l.customer_id) AS position FROM latest AS l) SELECT f.customer_id, f.position FROM final AS f",
            rule: "SQBRSQL018",
            relation_keys: r#"{"orders": [["order_id"]]}"#,
            expected_anchors: &[],
            expected_fixed_sql: None,
        },
        QualityRuleTestCase {
            description: "RANK ties are deterministic",
            sql: "SELECT RANK() OVER (ORDER BY o.ordered_at) AS rn FROM orders AS o",
            rule: "SQBRSQL018",
            relation_keys: "{}",
            expected_anchors: &[],
            expected_fixed_sql: None,
        },
        QualityRuleTestCase {
            description: "unused CTE output is removed",
            sql: "WITH orders AS (SELECT o.order_id, o.status, o.note FROM raw_orders AS o), final AS (SELECT r.order_id, r.status FROM orders AS r) SELECT f.order_id, f.status FROM final AS f",
            rule: "SQBRSQL042",
            relation_keys: "{}",
            expected_anchors: &["o.note"],
            expected_fixed_sql: Some(
                "WITH orders AS (SELECT o.order_id, o.status FROM raw_orders AS o), final AS (SELECT r.order_id, r.status FROM orders AS r) SELECT f.order_id, f.status FROM final AS f",
            ),
        },
        QualityRuleTestCase {
            description: "star pass-through into the final CTE keeps every column",
            sql: "WITH orders AS (SELECT o.order_id, o.note FROM raw_orders AS o), final AS (SELECT * FROM orders) SELECT * FROM final",
            rule: "SQBRSQL042",
            relation_keys: "{}",
            expected_anchors: &[],
            expected_fixed_sql: None,
        },
        QualityRuleTestCase {
            description: "star pass-through follows the reader's own reads",
            sql: "WITH orders AS (SELECT o.order_id, o.note FROM raw_orders AS o), staged AS (SELECT * FROM orders), final AS (SELECT s.order_id FROM staged AS s) SELECT f.order_id FROM final AS f",
            rule: "SQBRSQL042",
            relation_keys: "{}",
            expected_anchors: &["o.note"],
            expected_fixed_sql: Some(
                "WITH orders AS (SELECT o.order_id FROM raw_orders AS o), staged AS (SELECT * FROM orders), final AS (SELECT s.order_id FROM staged AS s) SELECT f.order_id FROM final AS f",
            ),
        },
        QualityRuleTestCase {
            description: "a same-named cast of a source column is not a lateral read",
            sql: "WITH orders AS (SELECT o.order_id, CAST(note AS VARCHAR) AS note, o.note || 'x' AS tagged FROM raw_orders AS o), final AS (SELECT r.order_id, r.tagged FROM orders AS r) SELECT f.order_id, f.tagged FROM final AS f",
            rule: "SQBRSQL042",
            relation_keys: "{}",
            expected_anchors: &["CAST(note AS VARCHAR) AS note"],
            expected_fixed_sql: Some(
                "WITH orders AS (SELECT o.order_id, o.note || 'x' AS tagged FROM raw_orders AS o), final AS (SELECT r.order_id, r.tagged FROM orders AS r) SELECT f.order_id, f.tagged FROM final AS f",
            ),
        },
        QualityRuleTestCase {
            description: "an interpolated expression in a reader may read any column",
            sql: "WITH orders AS (SELECT o.order_id, o.status FROM raw_orders AS o), final AS (SELECT r.order_id FROM orders AS r WHERE __sqlbuild_audit_parameter_0__) SELECT f.order_id FROM final AS f",
            rule: "SQBRSQL042",
            relation_keys: "{}",
            expected_anchors: &[],
            expected_fixed_sql: None,
        },
        QualityRuleTestCase {
            description: "an interpolated output is never reported",
            sql: "WITH orders AS (SELECT o.order_id, __SQB_LINT_0002 FROM raw_orders AS o), final AS (SELECT r.order_id FROM orders AS r) SELECT f.order_id FROM final AS f",
            rule: "SQBRSQL042",
            relation_keys: "{}",
            expected_anchors: &[],
            expected_fixed_sql: None,
        },
        QualityRuleTestCase {
            description: "DISTINCT CTE reports without a fix",
            sql: "WITH orders AS (SELECT DISTINCT o.order_id, o.note FROM raw_orders AS o), final AS (SELECT r.order_id FROM orders AS r) SELECT f.order_id FROM final AS f",
            rule: "SQBRSQL042",
            relation_keys: "{}",
            expected_anchors: &["o.note"],
            expected_fixed_sql: None,
        },
        QualityRuleTestCase {
            description: "columns read in later join and filter clauses are used",
            sql: "WITH orders AS (SELECT o.order_id, o.customer_id, o.status FROM raw_orders AS o), final AS (SELECT c.name FROM orders AS r INNER JOIN customers AS c ON r.customer_id = c.customer_id WHERE r.status = 'open' QUALIFY ROW_NUMBER() OVER (PARTITION BY r.order_id ORDER BY c.name) = 1) SELECT f.name FROM final AS f",
            rule: "SQBRSQL042",
            relation_keys: "{}",
            expected_anchors: &[],
            expected_fixed_sql: None,
        },
        QualityRuleTestCase {
            description: "a column read only through a nested star is used",
            sql: "WITH g AS (SELECT r.order_id, r.amount FROM raw_orders AS r), final AS (SELECT g.order_id, HASH(g.*) AS row_hash FROM g) SELECT f.order_id, f.row_hash FROM final AS f",
            rule: "SQBRSQL042",
            relation_keys: "{}",
            expected_anchors: &[],
            expected_fixed_sql: None,
        },
        QualityRuleTestCase {
            description: "a whole-row reference reads every column",
            sql: "WITH g AS (SELECT r.order_id, r.amount FROM raw_orders AS r), final AS (SELECT g.order_id, HASH(g) AS row_hash FROM g) SELECT f.order_id, f.row_hash FROM final AS f",
            rule: "SQBRSQL042",
            relation_keys: "{}",
            expected_anchors: &[],
            expected_fixed_sql: None,
        },
        QualityRuleTestCase {
            description: "COUNT(DISTINCT row) reads every column",
            sql: "WITH g AS (SELECT r.order_id, r.amount FROM raw_orders AS r), final AS (SELECT COUNT(DISTINCT g) AS n FROM g) SELECT f.n FROM final AS f",
            rule: "SQBRSQL042",
            relation_keys: "{}",
            expected_anchors: &[],
            expected_fixed_sql: None,
        },
        QualityRuleTestCase {
            description: "COLUMNS(*) reads every column",
            sql: "WITH g AS (SELECT r.order_id, r.amount FROM raw_orders AS r), final AS (SELECT g.order_id FROM g WHERE COLUMNS(*) IS NOT NULL) SELECT f.order_id FROM final AS f",
            rule: "SQBRSQL042",
            relation_keys: "{}",
            expected_anchors: &[],
            expected_fixed_sql: None,
        },
        QualityRuleTestCase {
            description: "COLUMNS with a pattern reads every column",
            sql: "WITH g AS (SELECT r.order_id, r.amount FROM raw_orders AS r), final AS (SELECT MAX(COLUMNS('order.*')) FROM g) SELECT * FROM final",
            rule: "SQBRSQL042",
            relation_keys: "{}",
            expected_anchors: &[],
            expected_fixed_sql: None,
        },
        QualityRuleTestCase {
            description: "DISTINCT star pass-through reads every column",
            sql: "WITH g AS (SELECT r.order_id, r.amount FROM raw_orders AS r), staged AS (SELECT DISTINCT * FROM g), final AS (SELECT s.order_id FROM staged AS s) SELECT f.order_id FROM final AS f",
            rule: "SQBRSQL042",
            relation_keys: "{}",
            expected_anchors: &[],
            expected_fixed_sql: None,
        },
        QualityRuleTestCase {
            description: "a positional ORDER BY over a star pass-through reads every column",
            sql: "WITH g AS (SELECT r.order_id, r.amount FROM raw_orders AS r), staged AS (SELECT * FROM g ORDER BY 2 LIMIT 1), final AS (SELECT s.order_id FROM staged AS s) SELECT f.order_id FROM final AS f",
            rule: "SQBRSQL042",
            relation_keys: "{}",
            expected_anchors: &[],
            expected_fixed_sql: None,
        },
        QualityRuleTestCase {
            description: "an output alias read in WHERE or GROUP BY is used",
            sql: "WITH g AS (SELECT r.order_id, r.amount * 2 AS doubled, r.customer_id % 2 AS bucket FROM raw_orders AS r WHERE doubled > 1 GROUP BY r.order_id, doubled, bucket), final AS (SELECT g.order_id FROM g) SELECT f.order_id FROM final AS f",
            rule: "SQBRSQL042",
            relation_keys: "{}",
            expected_anchors: &[],
            expected_fixed_sql: None,
        },
        QualityRuleTestCase {
            description: "GROUP BY ALL grouping column is reported without a fix",
            sql: "WITH g AS (SELECT r.customer_id, r.status, SUM(r.amount) AS total FROM raw_orders AS r GROUP BY ALL), final AS (SELECT g.customer_id, g.total FROM g) SELECT f.customer_id, f.total FROM final AS f",
            rule: "SQBRSQL042",
            relation_keys: "{}",
            expected_anchors: &["r.status"],
            expected_fixed_sql: None,
        },
        QualityRuleTestCase {
            description: "an aggregate in an ungrouped select is reported without a fix",
            sql: "WITH g AS (SELECT 'all' AS label, COUNT(*) AS n FROM raw_orders AS r), final AS (SELECT g.label FROM g) SELECT f.label FROM final AS f",
            rule: "SQBRSQL042",
            relation_keys: "{}",
            expected_anchors: &["COUNT(*) AS n"],
            expected_fixed_sql: None,
        },
        QualityRuleTestCase {
            description: "a set-returning projection is reported without a fix",
            sql: "WITH g AS (SELECT r.order_id, UNNEST(r.tags) AS tag FROM raw_orders AS r), final AS (SELECT g.order_id FROM g) SELECT f.order_id FROM final AS f",
            rule: "SQBRSQL042",
            relation_keys: "{}",
            expected_anchors: &["UNNEST(r.tags) AS tag"],
            expected_fixed_sql: None,
        },
        QualityRuleTestCase {
            description: "ORDER BY ALL with LIMIT is reported without a fix",
            sql: "WITH g AS (SELECT r.order_id, r.customer_id FROM raw_orders AS r ORDER BY ALL LIMIT 1), final AS (SELECT g.order_id FROM g) SELECT f.order_id FROM final AS f",
            rule: "SQBRSQL042",
            relation_keys: "{}",
            expected_anchors: &["r.customer_id"],
            expected_fixed_sql: None,
        },
        QualityRuleTestCase {
            description: "DISTINCT ON is reported without a fix",
            sql: "WITH g AS (SELECT DISTINCT ON (r.customer_id) r.order_id, r.amount FROM raw_orders AS r ORDER BY r.customer_id, r.order_id), final AS (SELECT g.order_id FROM g) SELECT f.order_id FROM final AS f",
            rule: "SQBRSQL042",
            relation_keys: "{}",
            expected_anchors: &["r.amount"],
            expected_fixed_sql: None,
        },
        QualityRuleTestCase {
            description: "a volatile projection is reported without a fix",
            sql: "WITH g AS (SELECT r.order_id, RANDOM() AS draw FROM raw_orders AS r), final AS (SELECT g.order_id FROM g) SELECT f.order_id FROM final AS f",
            rule: "SQBRSQL042",
            relation_keys: "{}",
            expected_anchors: &["RANDOM() AS draw"],
            expected_fixed_sql: None,
        },
        QualityRuleTestCase {
            description: "a deterministic scalar projection is removed",
            sql: "WITH g AS (SELECT r.order_id, COALESCE(UPPER(r.status), 'none') AS label FROM raw_orders AS r), final AS (SELECT g.order_id FROM g) SELECT f.order_id FROM final AS f",
            rule: "SQBRSQL042",
            relation_keys: "{}",
            expected_anchors: &["COALESCE(UPPER(r.status), 'none') AS label"],
            expected_fixed_sql: Some(
                "WITH g AS (SELECT r.order_id FROM raw_orders AS r), final AS (SELECT g.order_id FROM g) SELECT f.order_id FROM final AS f",
            ),
        },
    ];
    for test_case in &test_cases {
        let diagnostics: Vec<Value> = lint(test_case)?;
        assert_eq!(
            anchors(test_case.sql, &diagnostics),
            test_case.expected_anchors,
            "{}",
            test_case.description
        );
        assert_eq!(
            fixed(test_case.sql, &diagnostics).as_deref(),
            test_case.expected_fixed_sql,
            "{}",
            test_case.description
        );
    }
    Ok(())
}

#[test]
fn given_threshold_findings_when_linting_then_remediation_shows_the_exact_setting()
-> Result<(), String> {
    let test_cases = [
        QualityRemediationTestCase {
            description: "long literal points at a constant and the length setting",
            sql: "SELECT 'pending orders awaiting shipment' AS label",
            rule: "SQBRSQL044",
            expected_fragments: &[
                "reference it with `@const`",
                "(1) Only this model: add `constants (_status_pattern '<value>')`",
                "`_sqlbuild/_constants/` of the nearest folder",
                "(3) Use top-level `constants/` only",
                "the current value is 24",
                "[rules.thresholds]\n            max_literal_length = 32",
            ],
        },
        QualityRemediationTestCase {
            description: "long ranking sort points at a row key and the sort setting",
            sql: "SELECT ROW_NUMBER() OVER (PARTITION BY o.customer_id ORDER BY o.a, o.b, o.order_id) AS rn FROM orders AS o",
            rule: "SQBRSQL043",
            expected_fragments: &[
                "unique row key as the final tie-breaker",
                "HASH(source_partition, source_offset, line_index) AS row_key",
                "the current value is 2",
                "[rules.thresholds]\n            max_ranking_order_by = 3",
            ],
        },
        QualityRemediationTestCase {
            description: "unproven ranking points at upstream keys and a built row key",
            sql: "SELECT ROW_NUMBER() OVER (PARTITION BY o.customer_id ORDER BY o.a) AS rn FROM orders AS o",
            rule: "SQBRSQL018",
            expected_fragments: &[
                "a `unique` column audit on a column that is also non-null",
                "the `unique_key` of an incremental `merge` model",
                "HASH(source_partition, source_offset, line_index) AS row_key",
            ],
        },
    ];
    for test_case in &test_cases {
        let diagnostics: Vec<Value> = lint(&QualityRuleTestCase {
            description: test_case.description,
            sql: test_case.sql,
            rule: test_case.rule,
            relation_keys: "{}",
            expected_anchors: &[],
            expected_fixed_sql: None,
        })?;
        let remediation: &str = diagnostics
            .first()
            .and_then(|diagnostic| diagnostic["remediation"].as_str())
            .ok_or_else(|| format!("{}: no finding", test_case.description))?;
        let present: Vec<&str> = test_case
            .expected_fragments
            .iter()
            .copied()
            .filter(|fragment| remediation.contains(fragment))
            .collect();
        assert_eq!(
            present, test_case.expected_fragments,
            "{}: {remediation}",
            test_case.description
        );
    }
    Ok(())
}
