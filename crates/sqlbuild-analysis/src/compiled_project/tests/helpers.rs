use crate::compiled_project::models::{CompiledModelFacts, ModelAnalysisFact};

pub(super) fn model(name: &str, query_sql: &str) -> CompiledModelFacts {
    CompiledModelFacts {
        name: name.to_owned(),
        query_sql: query_sql.to_owned(),
        ..CompiledModelFacts::default()
    }
}

pub(super) fn analysis(column: &str) -> ModelAnalysisFact {
    ModelAnalysisFact {
        inferred_columns: vec![(column.to_owned(), Some("INTEGER".to_owned()))],
        dynamic_proof: None,
    }
}
