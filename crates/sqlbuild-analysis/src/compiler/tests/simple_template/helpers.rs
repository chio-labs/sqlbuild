use polyglot_sql::Dialect;

use crate::compiler::_helpers::sql_tests::planning::{AnalysisTemplate, parsed_analysis_template};
use crate::compiler::_helpers::sql_tests::simple_template::simple_analysis_template;
use crate::compiler::tests::test_types::SimpleTemplateCorpusOutcome;

pub(crate) fn simple_template_corpus_outcome() -> SimpleTemplateCorpusOutcome {
    let dialect = Dialect::get_by_name("duckdb").expect("DuckDB dialect");
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
            simple_analysis_template(&sql, "duckdb", &dialect).map(|facts| (sql, facts))
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
