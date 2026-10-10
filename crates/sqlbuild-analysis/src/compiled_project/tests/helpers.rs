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

pub(super) fn plain_check(
    sql: &str,
    keys: &[&str],
) -> crate::compiled_project::models::PlainModelCheck {
    use crate::compiled_project::models::{ModelLoopSettings, PlainModelCheck};
    PlainModelCheck {
        config_keys: keys.iter().map(|key| (*key).to_owned()).collect(),
        interpolated_sql: Some(sql.to_owned()),
        settings: ModelLoopSettings {
            sql_analysis: true,
            defer_sql_validation: true,
            ..ModelLoopSettings::default()
        },
        ..PlainModelCheck::default()
    }
}
