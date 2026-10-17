use std::collections::HashMap;
use std::sync::Mutex;

use polyglot_sql::Dialect;

use crate::compiler::_helpers::sql_tests::planning::{
    analysis_template, parsed_analysis_template, take_template_ast_parse_count,
};
use crate::compiler::_helpers::sql_tests::simple_template::simple_analysis_template;
use crate::compiler::tests::simple_template_helpers::simple_template_corpus_outcome;
use crate::compiler::tests::test_types::{SimpleTemplateCorpusTestCase, SimpleTemplateTestCase};

#[test]
fn given_bounded_and_fallback_queries_when_planning_then_facts_and_ast_counts_match() {
    let test_cases = [
        SimpleTemplateTestCase {
            description: "dense CTE projections joins and union remove one cold template AST",
            dialect: "duckdb",
            sql: r#"WITH imported AS (SELECT * FROM __ref("orders")),
lookup_0 AS (SELECT * FROM __source("customers")),
projected AS (SELECT CAST(b.id AS INTEGER) AS id,
CAST(b.amount + COALESCE(l0.amount, 0) AS DOUBLE) AS amount,
CAST(COALESCE(b.amount, 0) + CAST(b.id AS DOUBLE) AS DOUBLE) AS quantity
FROM imported AS b LEFT JOIN lookup_0 AS l0 ON l0.id = b.id),
combined AS (SELECT id, amount, quantity FROM projected
UNION ALL BY NAME SELECT id, amount, quantity FROM projected WHERE id = 0),
final AS (SELECT CAST(id AS INTEGER) AS id, CAST(amount AS DOUBLE) AS amount FROM combined)
SELECT id, amount FROM final"#,
            expected_ast_parses: 0,
        },
        SimpleTemplateTestCase {
            description: "nested CTEs follow outer relation then WITH traversal order",
            dialect: "duckdb",
            sql: "WITH recent AS (WITH nested AS (SELECT * FROM __source(\"orders\")) SELECT id FROM nested) SELECT id FROM recent JOIN __ref(\"customers\") AS c ON c.id = recent.id",
            expected_ast_parses: 0,
        },
        SimpleTemplateTestCase {
            description: "root union has no Select CTE names",
            dialect: "duckdb",
            sql: "SELECT id FROM __ref(\"orders\") UNION ALL SELECT id FROM __source(\"orders\")",
            expected_ast_parses: 0,
        },
        SimpleTemplateTestCase {
            description: "quoted names escapes and line-comment marker lookalikes",
            dialect: "duckdb",
            sql: "WITH \"recent\" AS (SELECT * FROM __ref(\"or\"\"ders\")) SELECT id FROM \"recent\" -- __seed(\"ignored\")",
            expected_ast_parses: 0,
        },
        SimpleTemplateTestCase {
            description: "two-part dbt references precede joined seeds",
            dialect: "duckdb",
            sql: "SELECT id FROM __dbt_ref(\"shop\", \"orders\") AS o JOIN __seed(\"regions\") AS r ON o.id = r.id",
            expected_ast_parses: 0,
        },
        SimpleTemplateTestCase {
            description: "scalar nested subquery retains full parser",
            dialect: "duckdb",
            sql: "SELECT (SELECT id FROM __ref(\"orders\")) AS id",
            expected_ast_parses: 1,
        },
        SimpleTemplateTestCase {
            description: "string marker lookalike retains full parser",
            dialect: "duckdb",
            sql: "SELECT '__ref(\"ignored\")' AS note FROM __ref(\"orders\")",
            expected_ast_parses: 1,
        },
        SimpleTemplateTestCase {
            description: "table function call retains full parser",
            dialect: "duckdb",
            sql: "SELECT id FROM __table_fn(\"orders\")(1)",
            expected_ast_parses: 1,
        },
        SimpleTemplateTestCase {
            description: "scalar function marker retains full parser",
            dialect: "duckdb",
            sql: "SELECT __udf(\"amount\")(id) AS id FROM __ref(\"orders\")",
            expected_ast_parses: 1,
        },
        SimpleTemplateTestCase {
            description: "WITH over UNION retains full parser AST attachment",
            dialect: "duckdb",
            sql: "WITH recent AS (SELECT id FROM orders) SELECT id FROM recent UNION ALL SELECT id FROM recent",
            expected_ast_parses: 1,
        },
        SimpleTemplateTestCase {
            description: "unterminated block comment retains full parser policy",
            dialect: "duckdb",
            sql: "SELECT id FROM __ref(\"orders\") /* unclosed",
            expected_ast_parses: 1,
        },
        SimpleTemplateTestCase {
            description: "nested block comments retain full parser policy",
            dialect: "duckdb",
            sql: "SELECT id FROM __ref(\"orders\") /* outer /* __ref(\"ignored\") */ inner */",
            expected_ast_parses: 1,
        },
        SimpleTemplateTestCase {
            description: "missing projection retains parser failure",
            dialect: "duckdb",
            sql: "SELECT FROM __ref(\"orders\")",
            expected_ast_parses: 1,
        },
        SimpleTemplateTestCase {
            description: "incomplete cast retains parser failure",
            dialect: "duckdb",
            sql: "SELECT CAST(id AS INTEGER FROM __ref(\"orders\")",
            expected_ast_parses: 1,
        },
        SimpleTemplateTestCase {
            description: "incomplete WHERE retains parser failure",
            dialect: "duckdb",
            sql: "SELECT id FROM __ref(\"orders\") WHERE",
            expected_ast_parses: 1,
        },
        SimpleTemplateTestCase {
            description: "unterminated identifier retains parser failure",
            dialect: "duckdb",
            sql: "SELECT id FROM __ref(\"orders)",
            expected_ast_parses: 1,
        },
        SimpleTemplateTestCase {
            description: "unterminated table identifier retains parser failure",
            dialect: "duckdb",
            sql: "SELECT id FROM \"orders",
            expected_ast_parses: 1,
        },
        SimpleTemplateTestCase {
            description: "incomplete join retains parser failure",
            dialect: "duckdb",
            sql: "SELECT id FROM __ref(\"orders\") LEFT",
            expected_ast_parses: 1,
        },
        SimpleTemplateTestCase {
            description: "multiple statements retain textual fallback",
            dialect: "duckdb",
            sql: "SELECT id FROM __ref(\"orders\"); SELECT id FROM other",
            expected_ast_parses: 1,
        },
        SimpleTemplateTestCase {
            description: "literal marker argument is not a Column",
            dialect: "duckdb",
            sql: "SELECT id FROM __ref('orders')",
            expected_ast_parses: 1,
        },
        SimpleTemplateTestCase {
            description: "postgres dollar quoting retains its parser",
            dialect: "postgres",
            sql: "SELECT $$__ref(\"ignored\")$$ AS note FROM __ref(\"orders\")",
            expected_ast_parses: 1,
        },
        SimpleTemplateTestCase {
            description: "snowflake quoted names retain its parser",
            dialect: "snowflake",
            sql: "SELECT id FROM __ref(\"orders\")",
            expected_ast_parses: 1,
        },
        SimpleTemplateTestCase {
            description: "bigquery backtick names retain its parser",
            dialect: "bigquery",
            sql: "SELECT id FROM __ref(`orders`)",
            expected_ast_parses: 1,
        },
        SimpleTemplateTestCase {
            description: "tsql brackets retain its parser",
            dialect: "tsql",
            sql: "SELECT id FROM __ref([orders])",
            expected_ast_parses: 1,
        },
        SimpleTemplateTestCase {
            description: "databricks quoting retains its parser",
            dialect: "databricks",
            sql: "SELECT id FROM __ref(`orders`)",
            expected_ast_parses: 1,
        },
    ];
    for test_case in test_cases {
        let dialect = Dialect::get_by_name(test_case.dialect).expect("supported test dialect");
        take_template_ast_parse_count();
        let expected = parsed_analysis_template(test_case.sql, &dialect);
        assert_eq!(
            take_template_ast_parse_count(),
            1,
            "{}",
            test_case.description
        );
        let fast = simple_analysis_template(test_case.sql, test_case.dialect, &dialect);
        assert_eq!(
            usize::from(fast.is_none()),
            test_case.expected_ast_parses,
            "{}",
            test_case.description
        );
        assert_eq!(
            fast.as_ref(),
            expected
                .as_ref()
                .filter(|_| test_case.expected_ast_parses == 0),
            "{}",
            test_case.description
        );
        let cache = Mutex::new(HashMap::new());
        let actual =
            analysis_template(test_case.sql, test_case.dialect, &cache).expect("template cache");
        assert_eq!(actual, expected, "{}", test_case.description);
        assert_eq!(
            take_template_ast_parse_count(),
            test_case.expected_ast_parses,
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_generated_and_mutated_queries_when_recognized_then_every_fact_matches_the_ast() {
    let test_cases = [SimpleTemplateCorpusTestCase {
        description: "combinations and token deletions preserve parser acceptance and facts",
        expected_min_recognized: 200,
        expected_mismatches: &[],
    }];
    for test_case in test_cases {
        let outcome = simple_template_corpus_outcome();
        assert!(
            outcome.recognized >= test_case.expected_min_recognized,
            "{}: {} recognized",
            test_case.description,
            outcome.recognized
        );
        assert_eq!(
            outcome.mismatches, test_case.expected_mismatches,
            "{}",
            test_case.description
        );
    }
}
