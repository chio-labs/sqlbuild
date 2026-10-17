use polyglot_sql::Dialect;
use polyglot_sql::parser::NO_PAREN_FUNCTION_NAMES;
use std::collections::HashMap;
use std::sync::Mutex;

use crate::compiler::_helpers::sql_tests::planning::{
    AnalysisTemplate, analysis_template, parsed_analysis_template,
};
use crate::compiler::_helpers::sql_tests::simple_template::simple_analysis_template;
use crate::compiler::tests::test_types::SimpleTemplateCorpusOutcome;

pub(crate) fn no_paren_marker_mismatches(dialect_name: &str) -> Vec<String> {
    let dialect = Dialect::get_by_name(dialect_name).expect("supported test dialect");
    let cache = Mutex::new(HashMap::new());
    NO_PAREN_FUNCTION_NAMES
        .iter()
        .flat_map(|name| [name.to_string(), name.to_ascii_lowercase()])
        .flat_map(|name| [name.clone(), format!("\"{name}\"")])
        .flat_map(|argument| {
            [
                format!("__ref({argument})"),
                format!("__source({argument})"),
                format!("__seed({argument})"),
                format!("__dbt_ref({argument})"),
                format!("__dbt_ref({argument}, \"orders\")"),
                format!("__dbt_ref(\"orders\", {argument})"),
            ]
        })
        .filter_map(|relation| {
            let sql = format!("SELECT id FROM {relation}");
            let fast = simple_analysis_template(&sql, dialect_name, &dialect);
            let expected = parsed_analysis_template(&sql, &dialect);
            let actual = analysis_template(&sql, dialect_name, &cache).expect("template cache");
            (fast.is_some()
                || actual != expected
                || expected
                    .as_ref()
                    .is_some_and(|facts| !facts.marker_calls.is_empty()))
            .then(|| format!("{sql}: fast={fast:?}, actual={actual:?}, expected={expected:?}"))
        })
        .collect()
}

pub(crate) fn simple_template_corpus_outcome(dialect_name: &str) -> SimpleTemplateCorpusOutcome {
    let dialect = Dialect::get_by_name(dialect_name).expect("supported test dialect");
    let mut queries: Vec<String> = Vec::new();
    for projection in [
        "id",
        "*",
        "CAST(id AS INTEGER) AS id",
        "COALESCE(id, 0) + id * 2 AS id",
        "CAST((id + 1) / 2 AS DOUBLE) AS id",
        "1.5 AS id",
        "\"__ref(ignored)\" AS id",
        "\"a\"\"b\" AS id",
    ] {
        for relation in [
            "__ref(\"orders\")",
            "__source(\"orders\")",
            "__seed(\"orders\")",
            "__dbt_ref(\"shop\", \"orders\")",
            "\"__ref\"(\"orders\")",
            "__REF(orders)",
            "\"__REF\"(\"orders\")",
            "__ref(final)",
            "__ref(\"a.b\")",
            "__ref(\"a\"\"b\")",
        ] {
            let body = format!("SELECT {projection} FROM {relation}");
            for sql in [
                body.clone(),
                format!("WITH recent AS ({body}) SELECT id FROM recent"),
                format!("{body} UNION ALL BY NAME {body}"),
                format!(
                    "WITH recent AS ({body}) SELECT id FROM __ref(\"customers\") AS c JOIN recent AS r ON c.id = r.id"
                ),
            ] {
                let tokens = dialect.tokenize(&sql).expect("generated SQL tokenizes");
                for token in &tokens {
                    queries.push(format!(
                        "{} {}",
                        &sql[..token.span.start],
                        &sql[token.span.end..]
                    ));
                    for inserted in [".", ")", "(", "FROM", "'__ref(\"ignored\")'"] {
                        queries.push(format!(
                            "{} {inserted} {}",
                            &sql[..token.span.start],
                            &sql[token.span.start..]
                        ));
                    }
                }
                queries.push(sql);
            }
        }
    }
    let recognized: Vec<(String, AnalysisTemplate)> = queries
        .into_iter()
        .filter_map(|sql| {
            simple_analysis_template(&sql, dialect_name, &dialect).map(|facts| (sql, facts))
        })
        .collect();
    SimpleTemplateCorpusOutcome {
        recognized: recognized.len(),
        mismatches: recognized
            .into_iter()
            .filter_map(|(sql, fast)| {
                let parsed = parsed_analysis_template(&sql, &dialect);
                (Some(&fast) != parsed.as_ref())
                    .then(|| format!("{sql}: fast={fast:?}, parsed={parsed:?}"))
            })
            .collect(),
    }
}
