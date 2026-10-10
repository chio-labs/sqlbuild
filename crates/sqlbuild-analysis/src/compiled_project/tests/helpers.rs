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

pub(super) fn column(
    column_type: Option<&str>,
    migrates: bool,
) -> crate::compiled_project::models::HeaderColumnShape {
    crate::compiled_project::models::HeaderColumnShape {
        column_type: column_type.map(str::to_owned),
        migrates,
    }
}

pub(super) fn splice(
    start: usize,
    end: usize,
    replacement: &str,
) -> crate::compiled_project::models::DeclarationSplice {
    crate::compiled_project::models::DeclarationSplice {
        start,
        end,
        replacement: replacement.to_owned(),
    }
}
