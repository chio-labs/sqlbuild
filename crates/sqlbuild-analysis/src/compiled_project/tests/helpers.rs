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
        ..ModelAnalysisFact::default()
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

pub(super) fn analysing_settings(
    sql_analysis: bool,
) -> crate::compiled_project::models::ModelLoopSettings {
    crate::compiled_project::models::ModelLoopSettings {
        sql_analysis,
        defer_sql_validation: true,
        ..crate::compiled_project::models::ModelLoopSettings::default()
    }
}

pub(super) fn python_312() -> sqlbuild_core::text::models::PythonText {
    sqlbuild_core::text::main::python_text::python_text((3, 12), "15.0.0")
        .expect("Python 3.12 is supported")
}

pub(super) fn legacy_schema_files(
    files: &[(&str, &[&str])],
) -> Vec<crate::compiled_project::models::LegacySchemaFile> {
    files
        .iter()
        .map(
            |(path, names)| crate::compiled_project::models::LegacySchemaFile {
                relative_path: (*path).to_owned(),
                model_names: names.iter().map(|name| (*name).to_owned()).collect(),
            },
        )
        .collect()
}

pub(super) fn generic_syntax() -> sqlbuild_sqltext::sql_scan::models::LexicalSyntax {
    sqlbuild_sqltext::sql_scan::models::LexicalSyntax {
        line_comment_prefixes: vec!["--".to_owned()],
        ..sqlbuild_sqltext::sql_scan::models::LexicalSyntax::default()
    }
}

pub(super) fn span(
    source_start: usize,
    source_end: usize,
    output_start: usize,
    output_end: usize,
) -> crate::compiled_project::models::SplicedSpan {
    crate::compiled_project::models::SplicedSpan {
        source_start,
        source_end,
        output_start,
        output_end,
    }
}
