use serde_json::{Value, json};

use crate::sql_lint::main::engine::lint_json;
use crate::sql_lint::main::formatter::format_json;
use crate::sql_lint::tests::{helpers, test_types};

#[test]
fn given_production_function_depth_when_linting_then_bounded_parser_accepts_it() {
    let test_cases = [test_types::FunctionDepthTestCase {
        description: "production depth remains supported",
        depth: 65,
        expected_diagnostic_count: 0,
    }];
    for test_case in test_cases {
        let sql = helpers::nested_function_sql(test_case.depth);
        let diagnostics = helpers::diagnostics(&sql).unwrap_or_else(|error| {
            panic!("{}: {error}", test_case.description);
        });
        assert_eq!(
            diagnostics.len(),
            test_case.expected_diagnostic_count,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_excessive_function_depth_when_linting_then_complexity_guard_rejects_it() {
    let test_cases = [test_types::FunctionDepthFailureTestCase {
        description: "excessive depth remains bounded",
        depth: 129,
        expected_code: "E_GUARD_FUNCTION_NESTING_DEPTH_EXCEEDED",
        expected_limit: "configured limit 128",
    }];
    for test_case in test_cases {
        let sql = helpers::nested_function_sql(test_case.depth);
        let error =
            helpers::diagnostics(&sql).expect_err("excessive nested calls should remain bounded");
        assert!(
            error.contains(test_case.expected_code),
            "{}",
            test_case.description
        );
        assert!(
            error.contains(test_case.expected_limit),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_sql_cases_when_linting_then_diagnostics_match() -> Result<(), String> {
    let test_cases = [
        test_types::LintTestCase {
            description: "NULL comparison",
            sql: "SELECT value FROM a WHERE value = NULL",
            expected_codes: &["SQBRSQL001"],
            expected_anchors: &[("SQBRSQL001", "=")],
        },
        test_types::LintTestCase {
            description: "wrapped NULL comparison",
            sql: "SELECT value FROM a WHERE (NULL) = value",
            expected_codes: &["SQBRSQL001"],
            expected_anchors: &[("SQBRSQL001", "=")],
        },
        test_types::LintTestCase {
            description: "implicit cartesian join",
            sql: "SELECT a.id FROM a, b",
            expected_codes: &["SQBRSQL002"],
            expected_anchors: &[("SQBRSQL002", ",")],
        },
        test_types::LintTestCase {
            description: "unconditioned join",
            sql: "SELECT a.id FROM a JOIN b",
            expected_codes: &["SQBRSQL003"],
            expected_anchors: &[("SQBRSQL003", "JOIN")],
        },
        test_types::LintTestCase {
            description: "unordered limit",
            sql: "SELECT id FROM items LIMIT 1",
            expected_codes: &["SQBRSQL004"],
            expected_anchors: &[("SQBRSQL004", "LIMIT")],
        },
        test_types::LintTestCase {
            description: "unused CTE",
            sql: "WITH unused AS (SELECT 1) SELECT 1",
            expected_codes: &["SQBRSQL005"],
            expected_anchors: &[("SQBRSQL005", "unused")],
        },
        test_types::LintTestCase {
            description: "unreachable CTE chain",
            sql: "WITH first AS (SELECT 1), second AS (SELECT * FROM first) SELECT 1",
            expected_codes: &["SQBRSQL005", "SQBRSQL005"],
            expected_anchors: &[],
        },
        test_types::LintTestCase {
            description: "unused CTE on set operation",
            sql: "WITH unused AS (SELECT 1 AS id) SELECT id FROM left_table UNION ALL SELECT id FROM right_table",
            expected_codes: &["SQBRSQL005"],
            expected_anchors: &[("SQBRSQL005", "unused")],
        },
        test_types::LintTestCase {
            description: "redundant distinct",
            sql: "SELECT DISTINCT id FROM items GROUP BY id",
            expected_codes: &["SQBRSQL006"],
            expected_anchors: &[("SQBRSQL006", "DISTINCT")],
        },
        test_types::LintTestCase {
            description: "aggregate distinct is not a select modifier",
            sql: "SELECT category, COUNT(DISTINCT id) FROM items GROUP BY category",
            expected_codes: &[],
            expected_anchors: &[],
        },
        test_types::LintTestCase {
            description: "positional set star",
            sql: "SELECT * FROM a UNION ALL SELECT * FROM b",
            expected_codes: &["SQBRSQL007"],
            expected_anchors: &[("SQBRSQL007", "UNION")],
        },
        test_types::LintTestCase {
            description: "parenthesized positional set star",
            sql: "(SELECT * FROM a) UNION ALL (SELECT id FROM b)",
            expected_codes: &["SQBRSQL007"],
            expected_anchors: &[("SQBRSQL007", "UNION")],
        },
        test_types::LintTestCase {
            description: "nested set wildcard does not contaminate outer set operation",
            sql: "SELECT 'actual' WHERE EXISTS (SELECT id FROM actual EXCEPT SELECT * FROM expected) UNION ALL SELECT 'expected'",
            expected_codes: &["SQBRSQL007"],
            expected_anchors: &[("SQBRSQL007", "EXCEPT")],
        },
        test_types::LintTestCase {
            description: "multiple statements",
            sql: "SELECT value FROM first LIMIT 1; SELECT value FROM second OFFSET 1",
            expected_codes: &["SQBRSQL004", "SQBRSQL004"],
            expected_anchors: &[("SQBRSQL004", "LIMIT"), ("SQBRSQL004", "OFFSET")],
        },
        test_types::LintTestCase {
            description: "nested query anchors",
            sql: "SELECT * FROM (SELECT id FROM inner_items ORDER BY id LIMIT 1) safe JOIN outer_items ON TRUE OFFSET 2",
            expected_codes: &["SQBRSQL003", "SQBRSQL004"],
            expected_anchors: &[("SQBRSQL003", "JOIN"), ("SQBRSQL004", "OFFSET")],
        },
        test_types::LintTestCase {
            description: "safe NULL predicate",
            sql: "SELECT value FROM a WHERE value IS NULL",
            expected_codes: &[],
            expected_anchors: &[],
        },
        test_types::LintTestCase {
            description: "NULL inside function",
            sql: "SELECT value FROM a WHERE COALESCE(value, NULL) = 1",
            expected_codes: &[],
            expected_anchors: &[],
        },
        test_types::LintTestCase {
            description: "NULL assignment",
            sql: "UPDATE items SET value = NULL",
            expected_codes: &[],
            expected_anchors: &[],
        },
        test_types::LintTestCase {
            description: "cross join",
            sql: "SELECT a.id FROM a CROSS JOIN b",
            expected_codes: &[],
            expected_anchors: &[],
        },
        test_types::LintTestCase {
            description: "keyed join",
            sql: "SELECT a.id FROM a JOIN b ON a.id = b.id",
            expected_codes: &[],
            expected_anchors: &[],
        },
        test_types::LintTestCase {
            description: "ordered limit",
            sql: "SELECT id FROM items ORDER BY id LIMIT 1",
            expected_codes: &[],
            expected_anchors: &[],
        },
        test_types::LintTestCase {
            description: "used CTE",
            sql: "WITH used AS (SELECT 1 AS id) SELECT id FROM used",
            expected_codes: &[],
            expected_anchors: &[],
        },
        test_types::LintTestCase {
            description: "group without distinct",
            sql: "SELECT id FROM items GROUP BY id",
            expected_codes: &[],
            expected_anchors: &[],
        },
        test_types::LintTestCase {
            description: "nonredundant distinct",
            sql: "SELECT DISTINCT a FROM items GROUP BY a, b",
            expected_codes: &[],
            expected_anchors: &[],
        },
        test_types::LintTestCase {
            description: "within group",
            sql: "SELECT DISTINCT LISTAGG(x, ',') WITHIN GROUP (ORDER BY x) FROM items",
            expected_codes: &[],
            expected_anchors: &[],
        },
        test_types::LintTestCase {
            description: "explicit positional set",
            sql: "SELECT id FROM a UNION ALL SELECT id FROM b",
            expected_codes: &[],
            expected_anchors: &[],
        },
        test_types::LintTestCase {
            description: "nested star outside set arms",
            sql: "SELECT id, name FROM (SELECT * FROM base) b UNION ALL SELECT id, name FROM other",
            expected_codes: &[],
            expected_anchors: &[],
        },
        test_types::LintTestCase {
            description: "nested star inside wrapped set arm",
            sql: "(SELECT id FROM (SELECT * FROM base) b) UNION ALL (SELECT id FROM other)",
            expected_codes: &[],
            expected_anchors: &[],
        },
    ];

    for test_case in &test_cases {
        let diagnostics = helpers::diagnostics(test_case.sql)?;
        let codes: Vec<&str> = diagnostics
            .iter()
            .filter_map(|item| item["code"].as_str())
            .collect();
        let anchors: Vec<(&str, &str)> = diagnostics
            .iter()
            .filter_map(|item| {
                let code = item["code"].as_str()?;
                let start = item["start"].as_u64()? as usize;
                let end = item["end"].as_u64()? as usize;
                Some((code, &test_case.sql[start..end]))
            })
            .collect();
        assert_eq!(codes, test_case.expected_codes, "{}", test_case.description);
        for expected_anchor in test_case.expected_anchors {
            assert!(
                anchors.contains(expected_anchor),
                "{}",
                test_case.description
            );
        }
    }
    Ok(())
}

#[test]
fn given_plain_sql_rules_when_linting_then_project_context_is_not_required() -> Result<(), String> {
    let test_cases = [
        test_types::PlainSqlLintTestCase {
            description: "trailing comment",
            sql: "SELECT id -- why\nFROM items",
            rule: "SQBRSQL033",
            expected_count: 1,
        },
        test_types::PlainSqlLintTestCase {
            description: "detached comment",
            sql: "SELECT id\n-- why\n\nFROM items",
            rule: "SQBRSQL033",
            expected_count: 1,
        },
        test_types::PlainSqlLintTestCase {
            description: "attached predicate comment",
            sql: "SELECT id FROM items WHERE active\n-- retain settled rows\nAND settled",
            rule: "SQBRSQL033",
            expected_count: 0,
        },
        test_types::PlainSqlLintTestCase {
            description: "attached CTE comment",
            sql: "WITH\n-- normalized rows\nnormalized AS (SELECT id FROM items)\nSELECT id FROM normalized",
            rule: "SQBRSQL033",
            expected_count: 0,
        },
        test_types::PlainSqlLintTestCase {
            description: "attached join comment",
            sql: "SELECT left_rows.id FROM left_rows\n-- match stable identities\nJOIN right_rows ON left_rows.id = right_rows.id",
            rule: "SQBRSQL033",
            expected_count: 0,
        },
        test_types::PlainSqlLintTestCase {
            description: "attached filter comment",
            sql: "SELECT id FROM items\n-- retain active rows\nWHERE active",
            rule: "SQBRSQL033",
            expected_count: 0,
        },
        test_types::PlainSqlLintTestCase {
            description: "attached projection comment",
            sql: "SELECT\n-- stable identity\nid\nFROM items",
            rule: "SQBRSQL033",
            expected_count: 0,
        },
        test_types::PlainSqlLintTestCase {
            description: "attached CASE branch comment",
            sql: "SELECT CASE\n-- settled outcome\nWHEN settled THEN 1 ELSE 0 END FROM items",
            rule: "SQBRSQL033",
            expected_count: 0,
        },
        test_types::PlainSqlLintTestCase {
            description: "attached ordering comment with Unicode and CRLF",
            sql: "SELECT id FROM items\r\n-- deterministic café order\r\nORDER BY id",
            rule: "SQBRSQL033",
            expected_count: 0,
        },
        test_types::PlainSqlLintTestCase {
            description: "block comment",
            sql: "SELECT id\n/* selected identity */\nFROM items",
            rule: "SQBRSQL033",
            expected_count: 1,
        },
        test_types::PlainSqlLintTestCase {
            description: "body without CTE",
            sql: "SELECT id FROM items",
            rule: "SQBRSQL034",
            expected_count: 1,
        },
        test_types::PlainSqlLintTestCase {
            description: "logic in terminal select",
            sql: "WITH final_rows AS (SELECT id FROM items) SELECT id FROM final_rows WHERE id > 0",
            rule: "SQBRSQL034",
            expected_count: 1,
        },
        test_types::PlainSqlLintTestCase {
            description: "terminal select reads wrong CTE",
            sql: "WITH first_rows AS (SELECT 1 AS id), final_rows AS (SELECT id FROM first_rows) SELECT id FROM first_rows",
            rule: "SQBRSQL035",
            expected_count: 1,
        },
        test_types::PlainSqlLintTestCase {
            description: "plain terminal select",
            sql: "WITH first_rows AS (SELECT 1 AS id), final_rows AS (SELECT id FROM first_rows) SELECT id FROM final_rows",
            rule: "SQBRSQL035",
            expected_count: 0,
        },
        test_types::PlainSqlLintTestCase {
            description: "nested CTE",
            sql: "SELECT id FROM (WITH nested_rows AS (SELECT 1 AS id) SELECT id FROM nested_rows)",
            rule: "SQBRSQL036",
            expected_count: 1,
        },
        test_types::PlainSqlLintTestCase {
            description: "recursive CTE",
            sql: "WITH RECURSIVE numbers AS (SELECT 1 UNION ALL SELECT 2) SELECT * FROM numbers",
            rule: "SQBRSQL037",
            expected_count: 1,
        },
        test_types::PlainSqlLintTestCase {
            description: "cross join",
            sql: "SELECT left_rows.id FROM left_rows CROSS JOIN right_rows",
            rule: "SQBRSQL038",
            expected_count: 1,
        },
    ];

    for test_case in test_cases {
        let diagnostics = helpers::diagnostics_for_rules(test_case.sql, &[test_case.rule])?;
        assert_eq!(
            diagnostics.len(),
            test_case.expected_count,
            "{}",
            test_case.description
        );
        assert!(
            diagnostics
                .iter()
                .all(|diagnostic| diagnostic["code"] == test_case.rule),
            "{}",
            test_case.description
        );
    }
    Ok(())
}

#[test]
fn given_native_rules_when_linting_then_diagnosis_and_remediation_are_actionable()
-> Result<(), String> {
    let test_cases = [
        test_types::LintMetadataTestCase {
            description: "NULL comparison guidance",
            sql: "SELECT value FROM a WHERE value = NULL",
            expected_code: "SQBRSQL001",
            expected_message: "Comparison with NULL is never true",
            expected_remediation: "Use IS NULL or IS NOT NULL when testing for NULL.",
        },
        test_types::LintMetadataTestCase {
            description: "implicit join guidance",
            sql: "SELECT a.id FROM a, b",
            expected_code: "SQBRSQL002",
            expected_message: "Comma-separated sources create an implicit cartesian join",
            expected_remediation: "Replace comma-separated sources with an explicit keyed join, or use CROSS JOIN when the cartesian product is intentional.",
        },
        test_types::LintMetadataTestCase {
            description: "unconditioned join guidance",
            sql: "SELECT a.id FROM a JOIN b",
            expected_code: "SQBRSQL003",
            expected_message: "Non-cross join has no meaningful condition",
            expected_remediation: "Add a meaningful ON or USING condition, or declare an intentional cartesian product with CROSS JOIN.",
        },
        test_types::LintMetadataTestCase {
            description: "unordered limit guidance",
            sql: "SELECT id FROM items LIMIT 1",
            expected_code: "SQBRSQL004",
            expected_message: "Row selection is nondeterministic",
            expected_remediation: "Add ORDER BY with a deterministic tie-breaker before LIMIT or OFFSET.",
        },
        test_types::LintMetadataTestCase {
            description: "unused CTE guidance",
            sql: "WITH unused AS (SELECT 1) SELECT 1",
            expected_code: "SQBRSQL005",
            expected_message: "CTE is unreachable from the final query",
            expected_remediation: "Reference the CTE from the final query or another reachable CTE, or remove it.",
        },
        test_types::LintMetadataTestCase {
            description: "redundant distinct guidance",
            sql: "SELECT DISTINCT id FROM items GROUP BY id",
            expected_code: "SQBRSQL006",
            expected_message: "DISTINCT is redundant with the grouped output",
            expected_remediation: "Remove DISTINCT; the equivalent GROUP BY already determines the output groups.",
        },
        test_types::LintMetadataTestCase {
            description: "positional set star guidance",
            sql: "SELECT * FROM a UNION ALL SELECT * FROM b",
            expected_code: "SQBRSQL007",
            expected_message: "Positional set operation is vulnerable to column-order drift",
            expected_remediation: "Enumerate columns in the same order in every set-operation branch.",
        },
    ];

    for test_case in test_cases {
        let diagnostics = helpers::diagnostics(test_case.sql)?;
        let diagnostic = diagnostics
            .first()
            .ok_or_else(|| format!("{} should report a diagnostic", test_case.description))?;
        assert_eq!(
            diagnostic["code"], test_case.expected_code,
            "{}",
            test_case.description
        );
        assert_eq!(
            diagnostic["message"], test_case.expected_message,
            "{}",
            test_case.description
        );
        assert_eq!(
            diagnostic["remediation"], test_case.expected_remediation,
            "{}",
            test_case.description
        );
        let start = diagnostic["start"].as_u64().unwrap_or_default();
        let end = diagnostic["end"].as_u64().unwrap_or_default();
        assert!(
            end > start,
            "{} should report a non-empty range",
            test_case.description
        );
    }
    Ok(())
}

#[test]
fn given_fixable_and_ambiguous_findings_when_linting_then_only_proven_edits_are_returned()
-> Result<(), String> {
    let test_cases = [
        test_types::LintFixTestCase {
            description: "right-hand NULL equality",
            sql: "SELECT value FROM a WHERE value = NULL",
            expected_code: "SQBRSQL001",
            expected_replacement: Some("IS"),
        },
        test_types::LintFixTestCase {
            description: "right-hand NULL inequality",
            sql: "SELECT value FROM a WHERE value <> NULL",
            expected_code: "SQBRSQL001",
            expected_replacement: Some("IS NOT"),
        },
        test_types::LintFixTestCase {
            description: "left-hand NULL comparison requires authored intent",
            sql: "SELECT value FROM a WHERE NULL = value",
            expected_code: "SQBRSQL001",
            expected_replacement: None,
        },
        test_types::LintFixTestCase {
            description: "plain conditionless join",
            sql: "SELECT a.id FROM a JOIN b",
            expected_code: "SQBRSQL003",
            expected_replacement: Some("CROSS JOIN"),
        },
        test_types::LintFixTestCase {
            description: "qualified conditionless join requires intent",
            sql: "SELECT a.id FROM a LEFT JOIN b",
            expected_code: "SQBRSQL003",
            expected_replacement: None,
        },
        test_types::LintFixTestCase {
            description: "conditionless semi join is never rewritten as cross join",
            sql: "SELECT a.id FROM a SEMI JOIN b",
            expected_code: "SQBRSQL003",
            expected_replacement: None,
        },
        test_types::LintFixTestCase {
            description: "redundant distinct",
            sql: "SELECT DISTINCT id FROM items GROUP BY id",
            expected_code: "SQBRSQL006",
            expected_replacement: Some(""),
        },
        test_types::LintFixTestCase {
            description: "single unused select CTE",
            sql: "WITH unused AS (SELECT 1) SELECT 1",
            expected_code: "SQBRSQL005",
            expected_replacement: Some(""),
        },
        test_types::LintFixTestCase {
            description: "reserved framework CTE is never deleted",
            sql: "WITH __expected__items AS (SELECT 1) SELECT 1",
            expected_code: "SQBRSQL005",
            expected_replacement: None,
        },
    ];

    for test_case in test_cases {
        let diagnostics = helpers::diagnostics(test_case.sql)?;
        let diagnostic = diagnostics
            .iter()
            .find(|item| item["code"] == test_case.expected_code)
            .ok_or_else(|| format!("{} should report", test_case.description))?;
        assert_eq!(
            diagnostic["fix"]["replacement"].as_str(),
            test_case.expected_replacement,
            "{}",
            test_case.description
        );
    }
    Ok(())
}

#[test]
fn given_additional_rule_cases_when_linting_then_findings_and_fixes_match() -> Result<(), String> {
    let test_cases = [
        test_types::AdditionalLintRuleTestCase {
            description: "bare union",
            sql: "SELECT 1 UNION SELECT 2",
            rule: "SQBRSQL008",
            expected_anchor: Some("UNION"),
            expected_replacement: Some("UNION DISTINCT"),
        },
        test_types::AdditionalLintRuleTestCase {
            description: "duplicate relation alias",
            sql: "SELECT x.id FROM alpha AS x JOIN beta AS x ON x.id = x.id",
            rule: "SQBRSQL009",
            expected_anchor: Some("x"),
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "duplicate output alias",
            sql: "SELECT a AS value, b AS value FROM items",
            rule: "SQBRSQL010",
            expected_anchor: Some("value"),
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "mixed grouping references",
            sql: "SELECT a, b FROM items GROUP BY 1, b",
            rule: "SQBRSQL011",
            expected_anchor: Some("GROUP"),
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "redundant else null",
            sql: "SELECT CASE WHEN a THEN b ELSE NULL END FROM items",
            rule: "SQBRSQL012",
            expected_anchor: Some("ELSE NULL"),
            expected_replacement: Some(""),
        },
        test_types::AdditionalLintRuleTestCase {
            description: "function-like distinct",
            sql: "SELECT DISTINCT(a) FROM items",
            rule: "SQBRSQL013",
            expected_anchor: Some("DISTINCT(a)"),
            expected_replacement: Some("DISTINCT a"),
        },
        test_types::AdditionalLintRuleTestCase {
            description: "constant scaffold predicate",
            sql: "SELECT a FROM items WHERE 1 = 1",
            rule: "SQBRSQL014",
            expected_anchor: Some("="),
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "consecutive statement terminator",
            sql: "SELECT 1;;",
            rule: "SQBRSQL015",
            expected_anchor: Some(";"),
            expected_replacement: Some(""),
        },
        test_types::AdditionalLintRuleTestCase {
            description: "redundant self alias",
            sql: "SELECT value AS value FROM items",
            rule: "SQBRSQL016",
            expected_anchor: Some(" AS value"),
            expected_replacement: Some(""),
        },
        test_types::AdditionalLintRuleTestCase {
            description: "constant row count",
            sql: "SELECT COUNT(1) FROM items",
            rule: "SQBRSQL017",
            expected_anchor: Some("1"),
            expected_replacement: Some("*"),
        },
        test_types::AdditionalLintRuleTestCase {
            description: "unordered row number",
            sql: "SELECT ROW_NUMBER() OVER (PARTITION BY id) FROM items",
            rule: "SQBRSQL018",
            expected_anchor: Some("ROW_NUMBER"),
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "literal null in not-in list",
            sql: "SELECT id FROM items WHERE id NOT IN (1, NULL)",
            rule: "SQBRSQL019",
            expected_anchor: Some("NOT"),
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "set branch arity mismatch",
            sql: "SELECT a, b FROM first UNION ALL SELECT c FROM second",
            rule: "SQBRSQL020",
            expected_anchor: Some("UNION"),
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "uncontrolled projection star",
            sql: "SELECT * FROM items",
            rule: "SQBRSQL021",
            expected_anchor: Some("*"),
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "unaliased calculated projection",
            sql: "SELECT price * quantity FROM items",
            rule: "SQBRSQL022",
            expected_anchor: Some("price"),
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "unused table alias",
            sql: "SELECT id FROM items AS unused",
            rule: "SQBRSQL023",
            expected_anchor: Some("AS unused"),
            expected_replacement: Some(""),
        },
        test_types::AdditionalLintRuleTestCase {
            description: "left join rejected in where",
            sql: "SELECT a.id FROM a LEFT JOIN b AS right_side ON a.id = right_side.id WHERE right_side.active = TRUE",
            rule: "SQBRSQL024",
            expected_anchor: Some("LEFT"),
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "implicit inner join",
            sql: "SELECT a.id FROM a JOIN b ON a.id = b.id",
            rule: "SQBRSQL025",
            expected_anchor: Some("JOIN"),
            expected_replacement: Some("INNER JOIN"),
        },
        test_types::AdditionalLintRuleTestCase {
            description: "mixed order directions",
            sql: "SELECT a, b FROM items ORDER BY a, b DESC",
            rule: "SQBRSQL026",
            expected_anchor: Some("ORDER"),
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "unqualified multi-source column",
            sql: "SELECT id FROM a JOIN b ON a.id = b.id",
            rule: "SQBRSQL027",
            expected_anchor: Some("id"),
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "mixed single-source qualification",
            sql: "SELECT items.id, name FROM items",
            rule: "SQBRSQL028",
            expected_anchor: Some("name"),
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "unknown relation qualifier",
            sql: "SELECT missing.id FROM items AS present",
            rule: "SQBRSQL029",
            expected_anchor: Some("missing"),
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "Snowflake shorthand cast type is not an unqualified column",
            sql: "SELECT src.value::STRING AS value FROM items AS src",
            rule: "SQBRSQL028",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "Snowflake JSON path and shorthand cast type are not columns",
            sql: "SELECT src.payload:item::TEXT AS item FROM items AS src",
            rule: "SQBRSQL028",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "Snowflake shorthand cast type is not a multi-source column",
            sql: "SELECT first.value::TEXT AS value FROM first JOIN second ON first.id = second.id",
            rule: "SQBRSQL027",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "implicit table alias is known in query scope",
            sql: "SELECT present.id FROM items present",
            rule: "SQBRSQL029",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "implicit joined alias contributes a selected value",
            sql: "SELECT left_side.id, right_side.name FROM alpha left_side LEFT JOIN beta right_side ON left_side.id = right_side.id",
            rule: "SQBRSQL032",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "Snowflake lateral flatten comma is explicit lateral syntax",
            sql: "SELECT flattened.value FROM items, LATERAL FLATTEN(input => items.payload) flattened",
            rule: "SQBRSQL002",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "Snowflake VALUES row separator is not a relation separator",
            sql: "SELECT column1 FROM VALUES (1), (2), (3)",
            rule: "SQBRSQL002",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "arithmetic multiplication is not a projected wildcard",
            sql: "SELECT price * quantity AS total FROM items",
            rule: "SQBRSQL021",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "number-led multiplication is not a projected wildcard",
            sql: "SELECT 100 * ratio AS percentage FROM items",
            rule: "SQBRSQL021",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "TOP projection wildcard remains controlled by star rule",
            sql: "SELECT TOP 10 * FROM items",
            rule: "SQBRSQL021",
            expected_anchor: Some("*"),
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "qualified wildcard modifier does not require an alias",
            sql: "SELECT src.* EXCLUDE (internal_id) FROM items AS src",
            rule: "SQBRSQL022",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "EXISTS literal projection does not require an alias",
            sql: "SELECT parent.id FROM parent WHERE EXISTS (SELECT 1 FROM child WHERE child.id = parent.id)",
            rule: "SQBRSQL022",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "correlated subquery can reference an outer relation",
            sql: "SELECT parent.id FROM parent WHERE EXISTS (SELECT 1 FROM child WHERE child.id = parent.id)",
            rule: "SQBRSQL029",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "Snowflake JSON path key is not a relation qualifier",
            sql: "SELECT PARSE_JSON(src.payload):item.name::VARCHAR AS item_name FROM items AS src",
            rule: "SQBRSQL029",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "Snowflake JSON path starts from a qualified relation value",
            sql: "SELECT parsed:item::VARCHAR AS item FROM items AS src, LATERAL FLATTEN(input => src.payload) AS parsed",
            rule: "SQBRSQL027",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "Snowflake ASOF JOIN alias is known in query scope",
            sql: "SELECT matched.ts FROM requested request ASOF JOIN available matched MATCH_CONDITION (request.ts >= matched.ts) ON request.id = matched.id",
            rule: "SQBRSQL029",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "later set branches inherit the first branch output name",
            sql: "SELECT 0 AS offset_value UNION ALL SELECT 1 UNION ALL SELECT 2",
            rule: "SQBRSQL022",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "scalar subquery output does not require an alias inside its scope",
            sql: "SELECT (SELECT MAX(child.value) FROM child WHERE child.id = parent.id) AS maximum_value FROM parent",
            rule: "SQBRSQL022",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "comma-derived table calculation still requires an alias",
            sql: "SELECT derived.value FROM items, (SELECT amount + tax FROM totals) AS derived",
            rule: "SQBRSQL022",
            expected_anchor: Some("amount"),
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "scalar subquery scope does not cross a prior statement",
            sql: "SELECT order_id FROM orders; SELECT invoice_id, (SELECT MAX(amount + tax) FROM totals) AS maximum_total FROM invoices",
            rule: "SQBRSQL022",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "contextual keyword remains a simple qualified projection",
            sql: "SELECT flattened.index FROM items AS src, LATERAL FLATTEN(input => src.payload) AS flattened",
            rule: "SQBRSQL022",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "generated expression sentinel is not an authored column",
            sql: "SELECT first.id FROM first JOIN second ON first.id = second.id WHERE __sqb_lint_0__",
            rule: "SQBRSQL027",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "null-safe comparison FROM is not a relation clause",
            sql: "SELECT CASE WHEN src.actual IS DISTINCT FROM src.expected THEN 1 ELSE 0 END AS differs FROM items AS src",
            rule: "SQBRSQL023",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "earlier projection alias is not a relation column",
            sql: "SELECT flattened.value AS item_index, item_index + 1 AS next_index FROM items AS src, LATERAL FLATTEN(input => src.payload) AS flattened",
            rule: "SQBRSQL027",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "current date context value is not a multi-source column",
            sql: "SELECT first_side.id FROM first_side JOIN second_side ON first_side.id = second_side.id WHERE first_side.created_at >= CURRENT_DATE",
            rule: "SQBRSQL027",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "current date context value does not mix qualification styles",
            sql: "SELECT first_side.id FROM first_side WHERE first_side.created_at >= CURRENT_DATE",
            rule: "SQBRSQL028",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "simple boolean case",
            sql: "SELECT CASE WHEN amount > 0 THEN TRUE ELSE FALSE END AS positive FROM items",
            rule: "SQBRSQL030",
            expected_anchor: Some("CASE WHEN amount > 0 THEN TRUE ELSE FALSE END"),
            expected_replacement: Some("COALESCE(amount > 0, FALSE)"),
        },
        test_types::AdditionalLintRuleTestCase {
            description: "unicode before simple boolean case preserves replacement text",
            sql: "SELECT 'é', CASE WHEN amount > 0 THEN TRUE ELSE FALSE END AS positive FROM items",
            rule: "SQBRSQL030",
            expected_anchor: Some("CASE WHEN amount > 0 THEN TRUE ELSE FALSE END"),
            expected_replacement: Some("COALESCE(amount > 0, FALSE)"),
        },
        test_types::AdditionalLintRuleTestCase {
            description: "commented boolean case is diagnosed without a fix",
            sql: "SELECT CASE WHEN amount /* reason */ > 0 THEN TRUE ELSE FALSE END FROM items",
            rule: "SQBRSQL030",
            expected_anchor: Some("CASE WHEN amount /* reason */ > 0 THEN TRUE ELSE FALSE END"),
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "multi-branch boolean case is diagnosed without an unsafe partial fix",
            sql: "SELECT CASE WHEN status = 'open' THEN TRUE WHEN priority = 'high' THEN TRUE ELSE FALSE END AS actionable FROM support_tickets",
            rule: "SQBRSQL030",
            expected_anchor: Some(
                "CASE WHEN status = 'open' THEN TRUE WHEN priority = 'high' THEN TRUE ELSE FALSE END",
            ),
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "case nested directly in else",
            sql: "SELECT CASE WHEN a THEN 1 ELSE CASE WHEN b THEN 2 END END FROM items",
            rule: "SQBRSQL031",
            expected_anchor: Some("CASE"),
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "joined relation contributes no values",
            sql: "SELECT a.id FROM a LEFT JOIN b ON a.id = b.id",
            rule: "SQBRSQL032",
            expected_anchor: Some("JOIN"),
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "joined relation contributes through an aggregate expression",
            sql: "SELECT ARRAY_AGG(b.value) AS values FROM a LEFT JOIN b ON a.id = b.id",
            rule: "SQBRSQL032",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "cross joined relation contributes through a filter predicate",
            sql: "SELECT orders.order_id FROM orders CROSS JOIN processing_cutoff AS cutoff WHERE orders.created_at < cutoff.created_at",
            rule: "SQBRSQL032",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "lateral relation contributes through a downstream join condition",
            sql: "SELECT orders.order_id, products.name FROM orders CROSS JOIN LATERAL UNNEST(orders.product_ids) AS item INNER JOIN products ON (products.product_id = item.product_id)",
            rule: "SQBRSQL032",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "explicit union is clean",
            sql: "SELECT 1 UNION ALL SELECT 2",
            rule: "SQBRSQL008",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "ordered row number is clean",
            sql: "SELECT ROW_NUMBER() OVER (PARTITION BY id ORDER BY created_at, id) FROM items",
            rule: "SQBRSQL018",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "equal set arity is clean",
            sql: "SELECT a, b FROM first UNION ALL SELECT c, d FROM second",
            rule: "SQBRSQL020",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "qualified alias is used",
            sql: "SELECT kept.id FROM items AS kept",
            rule: "SQBRSQL023",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "left join predicate retained in on is clean",
            sql: "SELECT a.id FROM a LEFT JOIN b ON a.id = b.id AND b.active = TRUE",
            rule: "SQBRSQL024",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "explicit inner join is clean",
            sql: "SELECT a.id FROM a INNER JOIN b ON a.id = b.id",
            rule: "SQBRSQL025",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "null literal inside not-in subquery expression is not a literal list",
            sql: "SELECT id FROM items WHERE id NOT IN (SELECT COALESCE(id, NULL) FROM other)",
            rule: "SQBRSQL019",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "left join null probe preserves unmatched rows",
            sql: "SELECT a.id FROM a LEFT JOIN b ON a.id = b.id WHERE b.id IS NULL",
            rule: "SQBRSQL024",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "left join predicate guarded by null probe preserves unmatched rows",
            sql: "SELECT a.id FROM a LEFT JOIN b ON a.id = b.id WHERE b.active = TRUE OR b.id IS NULL",
            rule: "SQBRSQL024",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "qualified catalog path is not treated as an unknown relation alias",
            sql: "SELECT catalog.schema.items.id FROM catalog.schema.items",
            rule: "SQBRSQL029",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "correlated subquery keeps outer table alias",
            sql: "SELECT id FROM items AS kept WHERE EXISTS (SELECT 1 FROM other WHERE other.id = kept.id)",
            rule: "SQBRSQL023",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "asof join is not rewritten as an inner join",
            sql: "SELECT a.id FROM a ASOF JOIN b ON a.id = b.id",
            rule: "SQBRSQL025",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "semi join is not rewritten as an inner join",
            sql: "SELECT a.id FROM a SEMI JOIN b ON a.id = b.id",
            rule: "SQBRSQL025",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "table alias carrying a column list is retained",
            sql: "SELECT a, b FROM items AS t(a, b)",
            rule: "SQBRSQL023",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "bracket list commas do not change set projection arity",
            sql: "SELECT a, [1, 2, 3] AS arr FROM t UNION ALL SELECT a, [4] AS arr FROM t",
            rule: "SQBRSQL020",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "quoted output alias is not redundant with an unquoted identifier",
            sql: "SELECT value AS \"value\" FROM items",
            rule: "SQBRSQL016",
            expected_anchor: None,
            expected_replacement: None,
        },
    ];

    for test_case in test_cases {
        let diagnostics = helpers::diagnostics_for_rules(test_case.sql, &[test_case.rule])?;
        assert_eq!(
            diagnostics.len(),
            usize::from(test_case.expected_anchor.is_some()),
            "{}",
            test_case.description
        );
        let _ = test_case.expected_anchor.map(|expected_anchor| {
            let diagnostic = &diagnostics[0];
            let start = diagnostic["start"].as_u64().unwrap_or_default() as usize;
            let end = diagnostic["end"].as_u64().unwrap_or_default() as usize;
            let source: String = test_case
                .sql
                .chars()
                .skip(start)
                .take(end - start)
                .collect();
            assert_eq!(source, expected_anchor, "{}", test_case.description);
            assert_eq!(
                diagnostic["fix"]["replacement"].as_str(),
                test_case.expected_replacement,
                "{}",
                test_case.description
            );
        });
    }
    Ok(())
}

#[test]
fn given_tsql_bare_union_when_linting_then_diagnostic_has_no_invalid_fix() -> Result<(), String> {
    let test_cases = [test_types::DialectLintRuleTestCase {
        description: "T-SQL bare UNION is diagnosed without an invalid fix",
        sql: "SELECT 1 UNION SELECT 2",
        dialect: "tsql",
        rule: "SQBRSQL008",
        expected_count: 1,
        expected_fix: false,
        expected_reason: "the active dialect does not accept explicit UNION DISTINCT",
    }];

    for test_case in test_cases {
        let diagnostics =
            helpers::diagnostics_for_dialect(test_case.sql, test_case.dialect, &[test_case.rule])?;
        assert_eq!(
            diagnostics.len(),
            test_case.expected_count,
            "{}",
            test_case.description
        );
        assert_eq!(
            diagnostics[0].get("fix").is_some(),
            test_case.expected_fix,
            "{}",
            test_case.description
        );
        assert_eq!(
            diagnostics[0]["fix_unavailable_reason"], test_case.expected_reason,
            "{}",
            test_case.description
        );
    }
    Ok(())
}

#[test]
fn given_format_cases_when_formatting_then_output_matches() -> Result<(), String> {
    let test_cases = [
        test_types::FormatTestCase {
            description: "comment-free canonical SQL",
            sql: "select a,b from items where a=1",
            expected_sql: "SELECT\n  a,\n  b\nFROM items\nWHERE\n  a = 1",
            expected_changed: true,
        },
        test_types::FormatTestCase {
            description: "lowercase function canonicalization preserves structure",
            sql: "select count(1) from items",
            expected_sql: "SELECT\n  COUNT(1)\nFROM items",
            expected_changed: true,
        },
        test_types::FormatTestCase {
            description: "block comment attachment",
            sql: "SELECT a, /* preserve */ b FROM items",
            expected_sql: "SELECT\n  a, /* preserve */\n  b\nFROM items",
            expected_changed: true,
        },
        test_types::FormatTestCase {
            description: "line and leading comments",
            sql: "-- lead\nselect a,b from items -- tail\nwhere a=1",
            expected_sql: "-- lead\nSELECT\n  a,\n  b\nFROM items -- tail\nWHERE\n  a = 1",
            expected_changed: true,
        },
        test_types::FormatTestCase {
            description: "standalone projection comments remain attached to following expressions",
            sql: "SELECT\n  -- first value\n  a,\n  -- second value\n  b\nFROM items",
            expected_sql: "SELECT\n  -- first value\n  a,\n  -- second value\n  b\nFROM items",
            expected_changed: false,
        },
        test_types::FormatTestCase {
            description: "comment marker string",
            sql: "select '-- not a comment' as value",
            expected_sql: "SELECT\n  '-- not a comment' AS value",
            expected_changed: true,
        },
        test_types::FormatTestCase {
            description: "doubled apostrophe string remains compiler compatible",
            sql: "select 'Customer''s order' as value",
            expected_sql: "SELECT\n  'Customer''s order' AS value",
            expected_changed: true,
        },
        test_types::FormatTestCase {
            description: "trailing comment",
            sql: "select a from items; -- retained",
            expected_sql: "SELECT\n  a\nFROM items -- retained\n",
            expected_changed: true,
        },
    ];

    for test_case in &test_cases {
        let response = format_json(
            &json!({"version": 1, "sql": test_case.sql, "dialect": "snowflake"}).to_string(),
        )?;
        let payload: Value = serde_json::from_str(&response).map_err(|error| error.to_string())?;
        assert_eq!(
            payload["sql"], test_case.expected_sql,
            "{}",
            test_case.description
        );
        assert_eq!(
            payload["changed"], test_case.expected_changed,
            "{}",
            test_case.description
        );
    }
    Ok(())
}

#[test]
fn given_unknown_rule_when_linting_then_request_is_rejected() -> Result<(), String> {
    let test_cases = [test_types::InvalidRuleTestCase {
        description: "unknown native lint rule",
        rule: "SQBRSQL999",
        expected_message: "unknown native lint rule 'SQBRSQL999'",
    }];

    for test_case in &test_cases {
        let request = json!({"version": 1, "sql": "SELECT 1", "dialect": "snowflake", "enabled_rules": [test_case.rule]}).to_string();
        let error = lint_json(&request)
            .err()
            .ok_or_else(|| "unknown rule should fail".to_string())?;
        assert!(
            error.contains(test_case.expected_message),
            "{}",
            test_case.description
        );
    }
    Ok(())
}
