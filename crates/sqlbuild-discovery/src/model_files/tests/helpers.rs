use crate::model_files::main::parse_model_text::parse_model_text;
use crate::model_files::models::{DiscoveredModelFile, ModelFileOptions};
use crate::model_files::tests::test_types::{Located, ModelSummary, Span};
use crate::models::LineColumnSpan;
use sqlbuild_core::text::main::python_text::python_text;

const FILE_PATH: &str = "/project/models/orders.sql";

fn options() -> ModelFileOptions {
    ModelFileOptions {
        supported_keys: [
            "audits",
            "columns",
            "constants",
            "description",
            "enums",
            "materialized",
            "tags",
            "unique_key",
        ]
        .into_iter()
        .map(str::to_owned)
        .collect(),
        removed_keys: vec!["run_despite_unchanged".to_owned()],
        extract_implicit_alias_columns: true,
        extract_output_column_locations: true,
        python: python_text((3, 12), "15.0.0").expect("Python 3.12 is supported"),
    }
}

fn located(locations: &[(String, LineColumnSpan)]) -> Vec<Located> {
    locations
        .iter()
        .map(|(name, span)| {
            (
                name.clone(),
                (span.line, span.column, span.end_line, span.end_column),
            )
        })
        .collect()
}

fn summary(model: &DiscoveredModelFile) -> (String, Vec<Located>, Vec<Located>) {
    (
        model.query_sql.clone(),
        located(&model.header_column_locations),
        located(&model.output_column_locations),
    )
}

/// Parse one model file as `/project/models/orders.sql` and summarise the outcome.
pub(super) fn parsed_summary(contents: &str) -> ModelSummary {
    parse_model_text(FILE_PATH, contents.to_owned(), &options())
        .map(|model| summary(&model))
        .map_err(|failure| (failure.message, failure.help))
}

/// The expected successful summary.
pub(super) fn parsed(
    query: &str,
    header: &[(&str, Span)],
    output: &[(&str, Span)],
) -> ModelSummary {
    Ok((query.to_owned(), owned(header), owned(output)))
}

fn owned(locations: &[(&str, Span)]) -> Vec<Located> {
    locations
        .iter()
        .map(|(name, span)| ((*name).to_owned(), *span))
        .collect()
}

/// The expected failure summary.
pub(super) fn failed(message: &str, help: Option<&str>) -> ModelSummary {
    Err((message.to_owned(), help.map(str::to_owned)))
}
