use crate::sql_lint::tests::{helpers, test_types};

#[test]
fn given_implicit_and_explicit_table_aliases_when_linting_then_unused_aliases_match()
-> Result<(), String> {
    let test_cases = [
        test_types::AdditionalLintRuleTestCase {
            description: "unused implicit table alias",
            sql: "SELECT id FROM items unused",
            rule: "SQBRSQL023",
            expected_anchor: Some("unused"),
            expected_replacement: Some(""),
        },
        test_types::AdditionalLintRuleTestCase {
            description: "unused implicit joined table alias",
            sql: "SELECT o.id FROM orders o INNER JOIN customers unused ON o.customer_id = o.id",
            rule: "SQBRSQL023",
            expected_anchor: Some("unused"),
            expected_replacement: Some(""),
        },
        test_types::AdditionalLintRuleTestCase {
            description: "unused implicit qualified table alias",
            sql: "SELECT id FROM warehouse.analytics.items unused",
            rule: "SQBRSQL023",
            expected_anchor: Some("unused"),
            expected_replacement: Some(""),
        },
        test_types::AdditionalLintRuleTestCase {
            description: "unused implicit subquery alias",
            sql: "SELECT id FROM (SELECT id FROM items) unused",
            rule: "SQBRSQL023",
            expected_anchor: Some("unused"),
            expected_replacement: Some(""),
        },
        test_types::AdditionalLintRuleTestCase {
            description: "unused implicit lateral table function alias",
            sql: "SELECT src.id FROM items src, LATERAL FLATTEN(input => src.payload) unused",
            rule: "SQBRSQL023",
            expected_anchor: Some("unused"),
            expected_replacement: Some(""),
        },
        test_types::AdditionalLintRuleTestCase {
            description: "used implicit table alias",
            sql: "SELECT kept.id FROM items kept",
            rule: "SQBRSQL023",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "used implicit joined table aliases",
            sql: "SELECT o.id, c.name FROM orders o INNER JOIN customers c ON o.customer_id = c.id",
            rule: "SQBRSQL023",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "used implicit qualified table alias",
            sql: "SELECT kept.id FROM warehouse.analytics.items kept",
            rule: "SQBRSQL023",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "used implicit subquery alias",
            sql: "SELECT sub.id FROM (SELECT id FROM items) sub",
            rule: "SQBRSQL023",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "used implicit lateral table function alias",
            sql: "SELECT flattened.value FROM items src, LATERAL FLATTEN(input => src.payload) flattened",
            rule: "SQBRSQL023",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "implicit alias used by correlated subquery",
            sql: "SELECT id FROM items kept WHERE EXISTS (SELECT 1 FROM other WHERE other.id = kept.id)",
            rule: "SQBRSQL023",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "implicit alias carrying a column list is retained",
            sql: "SELECT a FROM items t(a)",
            rule: "SQBRSQL023",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "qualified relation name is not an implicit alias",
            sql: "SELECT id FROM warehouse.analytics.items",
            rule: "SQBRSQL023",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "join modifier keywords are not implicit aliases",
            sql: "SELECT o.id, c.name FROM orders o POSITIONAL JOIN customers c",
            rule: "SQBRSQL023",
            expected_anchor: None,
            expected_replacement: None,
        },
        test_types::AdditionalLintRuleTestCase {
            description: "join condition identifiers are not implicit aliases",
            sql: "SELECT o.id, c.name FROM orders o INNER JOIN customers c USING (customer_id)",
            rule: "SQBRSQL023",
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
            assert_eq!(
                &test_case.sql[start..end],
                expected_anchor,
                "{}",
                test_case.description
            );
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
