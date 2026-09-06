use serde_json::{Value, json};

use crate::sql_lint::main::engine::lint_json;
use crate::sql_lint::main::formatter::format_json;
use crate::sql_lint::tests::{helpers, test_types};

#[test]
fn given_sql_cases_when_linting_then_diagnostics_match() -> Result<(), String> {
    let test_cases = [
        test_types::LintTestCase {
            description: "NULL comparison",
            sql: "SELECT value FROM a WHERE value = NULL",
            expected_codes: &["SQBL001"],
            expected_anchors: &[("SQBL001", "=")],
        },
        test_types::LintTestCase {
            description: "wrapped NULL comparison",
            sql: "SELECT value FROM a WHERE (NULL) = value",
            expected_codes: &["SQBL001"],
            expected_anchors: &[("SQBL001", "=")],
        },
        test_types::LintTestCase {
            description: "implicit cartesian join",
            sql: "SELECT a.id FROM a, b",
            expected_codes: &["SQBL002"],
            expected_anchors: &[("SQBL002", ",")],
        },
        test_types::LintTestCase {
            description: "unconditioned join",
            sql: "SELECT a.id FROM a JOIN b",
            expected_codes: &["SQBL003"],
            expected_anchors: &[("SQBL003", "JOIN")],
        },
        test_types::LintTestCase {
            description: "unordered limit",
            sql: "SELECT id FROM items LIMIT 1",
            expected_codes: &["SQBL004"],
            expected_anchors: &[("SQBL004", "LIMIT")],
        },
        test_types::LintTestCase {
            description: "unused CTE",
            sql: "WITH unused AS (SELECT 1) SELECT 1",
            expected_codes: &["SQBL005"],
            expected_anchors: &[("SQBL005", "unused")],
        },
        test_types::LintTestCase {
            description: "unreachable CTE chain",
            sql: "WITH first AS (SELECT 1), second AS (SELECT * FROM first) SELECT 1",
            expected_codes: &["SQBL005", "SQBL005"],
            expected_anchors: &[],
        },
        test_types::LintTestCase {
            description: "unused CTE on set operation",
            sql: "WITH unused AS (SELECT 1 AS id) SELECT id FROM left_table UNION ALL SELECT id FROM right_table",
            expected_codes: &["SQBL005"],
            expected_anchors: &[("SQBL005", "unused")],
        },
        test_types::LintTestCase {
            description: "redundant distinct",
            sql: "SELECT DISTINCT id FROM items GROUP BY id",
            expected_codes: &["SQBL006"],
            expected_anchors: &[("SQBL006", "DISTINCT")],
        },
        test_types::LintTestCase {
            description: "positional set star",
            sql: "SELECT * FROM a UNION ALL SELECT * FROM b",
            expected_codes: &["SQBL007"],
            expected_anchors: &[("SQBL007", "UNION")],
        },
        test_types::LintTestCase {
            description: "parenthesized positional set star",
            sql: "(SELECT * FROM a) UNION ALL (SELECT id FROM b)",
            expected_codes: &["SQBL007"],
            expected_anchors: &[("SQBL007", "UNION")],
        },
        test_types::LintTestCase {
            description: "multiple statements",
            sql: "SELECT value FROM first LIMIT 1; SELECT value FROM second OFFSET 1",
            expected_codes: &["SQBL004", "SQBL004"],
            expected_anchors: &[("SQBL004", "LIMIT"), ("SQBL004", "OFFSET")],
        },
        test_types::LintTestCase {
            description: "nested query anchors",
            sql: "SELECT * FROM (SELECT id FROM inner_items ORDER BY id LIMIT 1) safe JOIN outer_items ON TRUE OFFSET 2",
            expected_codes: &["SQBL003", "SQBL004"],
            expected_anchors: &[("SQBL003", "JOIN"), ("SQBL004", "OFFSET")],
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
fn given_native_rules_when_linting_then_diagnosis_and_remediation_are_actionable()
-> Result<(), String> {
    let test_cases = [
        test_types::LintMetadataTestCase {
            description: "NULL comparison guidance",
            sql: "SELECT value FROM a WHERE value = NULL",
            expected_code: "SQBL001",
            expected_message: "Comparison with NULL is never true",
            expected_remediation: "Use IS NULL or IS NOT NULL when testing for NULL.",
        },
        test_types::LintMetadataTestCase {
            description: "implicit join guidance",
            sql: "SELECT a.id FROM a, b",
            expected_code: "SQBL002",
            expected_message: "Comma-separated sources create an implicit cartesian join",
            expected_remediation: "Replace comma-separated sources with an explicit keyed join, or use CROSS JOIN when the cartesian product is intentional.",
        },
        test_types::LintMetadataTestCase {
            description: "unconditioned join guidance",
            sql: "SELECT a.id FROM a JOIN b",
            expected_code: "SQBL003",
            expected_message: "Non-cross join has no meaningful condition",
            expected_remediation: "Add a meaningful ON or USING condition, or declare an intentional cartesian product with CROSS JOIN.",
        },
        test_types::LintMetadataTestCase {
            description: "unordered limit guidance",
            sql: "SELECT id FROM items LIMIT 1",
            expected_code: "SQBL004",
            expected_message: "Row selection is nondeterministic",
            expected_remediation: "Add ORDER BY with a deterministic tie-breaker before LIMIT or OFFSET.",
        },
        test_types::LintMetadataTestCase {
            description: "unused CTE guidance",
            sql: "WITH unused AS (SELECT 1) SELECT 1",
            expected_code: "SQBL005",
            expected_message: "CTE is unreachable from the final query",
            expected_remediation: "Reference the CTE from the final query or another reachable CTE, or remove it.",
        },
        test_types::LintMetadataTestCase {
            description: "redundant distinct guidance",
            sql: "SELECT DISTINCT id FROM items GROUP BY id",
            expected_code: "SQBL006",
            expected_message: "DISTINCT is redundant with the grouped output",
            expected_remediation: "Remove DISTINCT; the equivalent GROUP BY already determines the output groups.",
        },
        test_types::LintMetadataTestCase {
            description: "positional set star guidance",
            sql: "SELECT * FROM a UNION ALL SELECT * FROM b",
            expected_code: "SQBL007",
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
            expected_code: "SQBL001",
            expected_replacement: Some("IS"),
        },
        test_types::LintFixTestCase {
            description: "right-hand NULL inequality",
            sql: "SELECT value FROM a WHERE value <> NULL",
            expected_code: "SQBL001",
            expected_replacement: Some("IS NOT"),
        },
        test_types::LintFixTestCase {
            description: "left-hand NULL comparison requires authored intent",
            sql: "SELECT value FROM a WHERE NULL = value",
            expected_code: "SQBL001",
            expected_replacement: None,
        },
        test_types::LintFixTestCase {
            description: "plain conditionless join",
            sql: "SELECT a.id FROM a JOIN b",
            expected_code: "SQBL003",
            expected_replacement: Some("CROSS JOIN"),
        },
        test_types::LintFixTestCase {
            description: "qualified conditionless join requires intent",
            sql: "SELECT a.id FROM a LEFT JOIN b",
            expected_code: "SQBL003",
            expected_replacement: None,
        },
        test_types::LintFixTestCase {
            description: "conditionless semi join is never rewritten as cross join",
            sql: "SELECT a.id FROM a SEMI JOIN b",
            expected_code: "SQBL003",
            expected_replacement: None,
        },
        test_types::LintFixTestCase {
            description: "redundant distinct",
            sql: "SELECT DISTINCT id FROM items GROUP BY id",
            expected_code: "SQBL006",
            expected_replacement: Some(""),
        },
        test_types::LintFixTestCase {
            description: "single unused select CTE",
            sql: "WITH unused AS (SELECT 1) SELECT 1",
            expected_code: "SQBL005",
            expected_replacement: Some(""),
        },
        test_types::LintFixTestCase {
            description: "reserved framework CTE is never deleted",
            sql: "WITH __expected__items AS (SELECT 1) SELECT 1",
            expected_code: "SQBL005",
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
            rule: "SQBL008",
            expected_anchor: Some("UNION"),
            expected_replacement: Some("UNION DISTINCT"),
        },
        test_types::AdditionalLintRuleTestCase {
            description: "duplicate relation alias",
            sql: "SELECT x.id FROM alpha AS x JOIN beta AS x ON x.id = x.id",
            rule: "SQBL009",
            expected_anchor: Some("x"),
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "duplicate output alias",
            sql: "SELECT a AS value, b AS value FROM items",
            rule: "SQBL010",
            expected_anchor: Some("value"),
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "mixed grouping references",
            sql: "SELECT a, b FROM items GROUP BY 1, b",
            rule: "SQBL011",
            expected_anchor: Some("GROUP"),
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "redundant else null",
            sql: "SELECT CASE WHEN a THEN b ELSE NULL END FROM items",
            rule: "SQBL012",
            expected_anchor: Some("ELSE NULL"),
            expected_replacement: Some(""),
        },
        test_types::AdditionalLintRuleTestCase {
            description: "function-like distinct",
            sql: "SELECT DISTINCT(a) FROM items",
            rule: "SQBL013",
            expected_anchor: Some("DISTINCT(a)"),
            expected_replacement: Some("DISTINCT a"),
        },
        test_types::AdditionalLintRuleTestCase {
            description: "constant scaffold predicate",
            sql: "SELECT a FROM items WHERE 1 = 1",
            rule: "SQBL014",
            expected_anchor: Some("="),
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "consecutive statement terminator",
            sql: "SELECT 1;;",
            rule: "SQBL015",
            expected_anchor: Some(";"),
            expected_replacement: Some(""),
        },
        test_types::AdditionalLintRuleTestCase {
            description: "redundant self alias",
            sql: "SELECT value AS value FROM items",
            rule: "SQBL016",
            expected_anchor: Some(" AS value"),
            expected_replacement: Some(""),
        },
        test_types::AdditionalLintRuleTestCase {
            description: "constant row count",
            sql: "SELECT COUNT(1) FROM items",
            rule: "SQBL017",
            expected_anchor: Some("1"),
            expected_replacement: Some("*"),
        },
        test_types::AdditionalLintRuleTestCase {
            description: "unordered row number",
            sql: "SELECT ROW_NUMBER() OVER (PARTITION BY id) FROM items",
            rule: "SQBL018",
            expected_anchor: Some("ROW_NUMBER"),
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "literal null in not-in list",
            sql: "SELECT id FROM items WHERE id NOT IN (1, NULL)",
            rule: "SQBL019",
            expected_anchor: Some("NOT"),
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "set branch arity mismatch",
            sql: "SELECT a, b FROM first UNION ALL SELECT c FROM second",
            rule: "SQBL020",
            expected_anchor: Some("UNION"),
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "uncontrolled projection star",
            sql: "SELECT * FROM items",
            rule: "SQBL021",
            expected_anchor: Some("*"),
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "unaliased calculated projection",
            sql: "SELECT price * quantity FROM items",
            rule: "SQBL022",
            expected_anchor: Some("price"),
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "unused table alias",
            sql: "SELECT id FROM items AS unused",
            rule: "SQBL023",
            expected_anchor: Some("AS unused"),
            expected_replacement: Some(""),
        },
        test_types::AdditionalLintRuleTestCase {
            description: "left join rejected in where",
            sql: "SELECT a.id FROM a LEFT JOIN b AS right_side ON a.id = right_side.id WHERE right_side.active = TRUE",
            rule: "SQBL024",
            expected_anchor: Some("LEFT"),
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "implicit inner join",
            sql: "SELECT a.id FROM a JOIN b ON a.id = b.id",
            rule: "SQBL025",
            expected_anchor: Some("JOIN"),
            expected_replacement: Some("INNER JOIN"),
        },
        test_types::AdditionalLintRuleTestCase {
            description: "mixed order directions",
            sql: "SELECT a, b FROM items ORDER BY a, b DESC",
            rule: "SQBL026",
            expected_anchor: Some("ORDER"),
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "unqualified multi-source column",
            sql: "SELECT id FROM a JOIN b ON a.id = b.id",
            rule: "SQBL027",
            expected_anchor: Some("id"),
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "mixed single-source qualification",
            sql: "SELECT items.id, name FROM items",
            rule: "SQBL028",
            expected_anchor: Some("name"),
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "unknown relation qualifier",
            sql: "SELECT missing.id FROM items AS present",
            rule: "SQBL029",
            expected_anchor: Some("missing"),
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "simple boolean case",
            sql: "SELECT CASE WHEN amount > 0 THEN TRUE ELSE FALSE END AS positive FROM items",
            rule: "SQBL030",
            expected_anchor: Some("CASE WHEN amount > 0 THEN TRUE ELSE FALSE END"),
            expected_replacement: Some("COALESCE(amount > 0, FALSE)"),
        },
        test_types::AdditionalLintRuleTestCase {
            description: "unicode before simple boolean case preserves replacement text",
            sql: "SELECT 'é', CASE WHEN amount > 0 THEN TRUE ELSE FALSE END AS positive FROM items",
            rule: "SQBL030",
            expected_anchor: Some("CASE WHEN amount > 0 THEN TRUE ELSE FALSE END"),
            expected_replacement: Some("COALESCE(amount > 0, FALSE)"),
        },
        test_types::AdditionalLintRuleTestCase {
            description: "commented boolean case is diagnosed without a fix",
            sql: "SELECT CASE WHEN amount /* reason */ > 0 THEN TRUE ELSE FALSE END FROM items",
            rule: "SQBL030",
            expected_anchor: Some("CASE WHEN amount /* reason */ > 0 THEN TRUE ELSE FALSE END"),
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "case nested directly in else",
            sql: "SELECT CASE WHEN a THEN 1 ELSE CASE WHEN b THEN 2 END END FROM items",
            rule: "SQBL031",
            expected_anchor: Some("CASE"),
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "joined relation contributes no values",
            sql: "SELECT a.id FROM a LEFT JOIN b ON a.id = b.id",
            rule: "SQBL032",
            expected_anchor: Some("JOIN"),
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "explicit union is clean",
            sql: "SELECT 1 UNION ALL SELECT 2",
            rule: "SQBL008",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "ordered row number is clean",
            sql: "SELECT ROW_NUMBER() OVER (PARTITION BY id ORDER BY created_at, id) FROM items",
            rule: "SQBL018",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "equal set arity is clean",
            sql: "SELECT a, b FROM first UNION ALL SELECT c, d FROM second",
            rule: "SQBL020",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "qualified alias is used",
            sql: "SELECT kept.id FROM items AS kept",
            rule: "SQBL023",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "left join predicate retained in on is clean",
            sql: "SELECT a.id FROM a LEFT JOIN b ON a.id = b.id AND b.active = TRUE",
            rule: "SQBL024",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "explicit inner join is clean",
            sql: "SELECT a.id FROM a INNER JOIN b ON a.id = b.id",
            rule: "SQBL025",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "null literal inside not-in subquery expression is not a literal list",
            sql: "SELECT id FROM items WHERE id NOT IN (SELECT COALESCE(id, NULL) FROM other)",
            rule: "SQBL019",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "left join null probe preserves unmatched rows",
            sql: "SELECT a.id FROM a LEFT JOIN b ON a.id = b.id WHERE b.id IS NULL",
            rule: "SQBL024",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "left join predicate guarded by null probe preserves unmatched rows",
            sql: "SELECT a.id FROM a LEFT JOIN b ON a.id = b.id WHERE b.active = TRUE OR b.id IS NULL",
            rule: "SQBL024",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "qualified catalog path is not treated as an unknown relation alias",
            sql: "SELECT catalog.schema.items.id FROM catalog.schema.items",
            rule: "SQBL029",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "correlated subquery keeps outer table alias",
            sql: "SELECT id FROM items AS kept WHERE EXISTS (SELECT 1 FROM other WHERE other.id = kept.id)",
            rule: "SQBL023",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "asof join is not rewritten as an inner join",
            sql: "SELECT a.id FROM a ASOF JOIN b ON a.id = b.id",
            rule: "SQBL025",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "semi join is not rewritten as an inner join",
            sql: "SELECT a.id FROM a SEMI JOIN b ON a.id = b.id",
            rule: "SQBL025",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "table alias carrying a column list is retained",
            sql: "SELECT a, b FROM items AS t(a, b)",
            rule: "SQBL023",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "bracket list commas do not change set projection arity",
            sql: "SELECT a, [1, 2, 3] AS arr FROM t UNION ALL SELECT a, [4] AS arr FROM t",
            rule: "SQBL020",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "quoted output alias is not redundant with an unquoted identifier",
            sql: "SELECT value AS \"value\" FROM items",
            rule: "SQBL016",
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
        rule: "SQBL008",
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
            description: "comment marker string",
            sql: "select '-- not a comment' as value",
            expected_sql: "SELECT\n  '-- not a comment' AS value",
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
        rule: "SQBL999",
        expected_message: "unknown native lint rule 'SQBL999'",
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
