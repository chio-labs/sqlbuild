//! Scenario marker text and failure-order regression coverage.

use crate::planner_scenario::main::replace_markers::replace_markers;
use crate::planner_scenario::tests::test_types::MarkerTestCase;
use sqlbuild_sqltext::sql_scan::models::LexicalSyntax;

#[test]
fn given_scenario_markers_when_resolving_then_preserves_authored_text_and_legacy_dbt_policy() {
    let test_cases = [
        MarkerTestCase {
            description: "Unicode markers preserve comments and aliases",
            sql: "SELECT 'é', * FROM __ref(\"订单\") x -- __ref(\"ignored\")",
            kind: 0,
            scanned: true,
            expected_sql: Ok("SELECT 'é', * FROM target_订单 x -- __ref(\"ignored\")"),
        },
        MarkerTestCase {
            description: "model dbt refs retain legacy unscanned substitution",
            sql: "SELECT '__dbt_ref(\"orders\")'",
            kind: 3,
            scanned: false,
            expected_sql: Ok("SELECT 'target_orders'"),
        },
        MarkerTestCase {
            description: "check dbt refs preserve string literals",
            sql: "SELECT '__dbt_ref(\"orders\")'",
            kind: 3,
            scanned: true,
            expected_sql: Ok("SELECT '__dbt_ref(\"orders\")'"),
        },
        MarkerTestCase {
            description: "dbt refs accept Python whitespace grammar",
            sql: "SELECT * FROM __dbt_ref(\"shop\"\u{1c},\u{2003}\"orders\")",
            kind: 3,
            scanned: true,
            expected_sql: Ok("SELECT * FROM target_shop__orders"),
        },
        MarkerTestCase {
            description: "uppercase dbt calls stay authored",
            sql: "SELECT * FROM __DBT_REF(\"orders\")",
            kind: 3,
            scanned: true,
            expected_sql: Ok("SELECT * FROM __DBT_REF(\"orders\")"),
        },
        MarkerTestCase {
            description: "unterminated strings fail scanning",
            sql: "SELECT 'unterminated",
            kind: 0,
            scanned: true,
            expected_sql: Err("failure"),
        },
    ];
    for test_case in test_cases {
        let syntax = test_case.scanned.then(|| LexicalSyntax {
            line_comment_prefixes: vec!["--".to_owned()],
            ..LexicalSyntax::default()
        });
        let actual = replace_markers(test_case.sql, test_case.kind, syntax, |name, _| {
            Ok::<_, ()>(format!("target_{name}"))
        })
        .map_err(|_| "failure");
        assert_eq!(
            actual.as_deref(),
            test_case.expected_sql.map_err(|_| &"failure"),
            "{}",
            test_case.description
        );
    }
}
