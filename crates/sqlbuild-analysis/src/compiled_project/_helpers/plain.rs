//! Deciding whether the native loop finishes a model, and finishing it.

use crate::compiled_project::constants::{HEADER_METADATA_KEYS, MACRO_TOKEN, NATIVE_HEADER_KEYS};
use crate::compiled_project::models::{
    AnalysisOverride, CompiledModelFacts, DescriptionShape, HeaderColumnShape, PlainModel,
    PlainModelBlocker, PlainModelCheck,
};

pub(crate) fn plain_model_blocker(check: &PlainModelCheck) -> Option<PlainModelBlocker> {
    if check.interpolated_sql.is_none() {
        return Some(PlainModelBlocker::Interpolation);
    }
    if check.settings.legacy_schema_files {
        return Some(PlainModelBlocker::LegacySchemaFiles);
    }
    if !check.settings.defer_sql_validation {
        return Some(PlainModelBlocker::ImmediateSqlValidation);
    }
    if !analysis_enabled(check) {
        return Some(PlainModelBlocker::SqlAnalysisDisabled);
    }
    if check.declaration_scan_failed {
        return Some(PlainModelBlocker::DeclarationScan);
    }
    let attachment_metadata: bool = check.config_keys.iter().any(|key| {
        HEADER_METADATA_KEYS.contains(&key.as_str()) && !NATIVE_HEADER_KEYS.contains(&key.as_str())
    });
    if attachment_metadata || check.description == DescriptionShape::Invalid {
        return Some(PlainModelBlocker::HeaderMetadata);
    }
    None
}

/// The project setting with the model's override applied; an ambiguous override is not plain.
fn analysis_enabled(check: &PlainModelCheck) -> bool {
    let settings = check.settings;
    let enabled: bool = match check.analysis_override {
        AnalysisOverride::Inherit => settings.sql_analysis,
        AnalysisOverride::Enabled => true,
        AnalysisOverride::Disabled | AnalysisOverride::Ambiguous => false,
    };
    settings.sql_analysis && !settings.no_sql_validation && enabled
}

/// Whether declaration-expanded SQL still calls macros.
pub(crate) fn calls_macros(sql: &str) -> bool {
    sql.contains(MACRO_TOKEN)
}

/// Enum-typed columns and column migrations still need the attachment's checks.
pub(crate) fn header_column_blocker(
    columns: &[HeaderColumnShape],
    enum_names: &[String],
) -> Option<PlainModelBlocker> {
    if columns.iter().any(|column| column.migrates) {
        return Some(PlainModelBlocker::ColumnMigrations);
    }
    let enum_typed: bool = columns.iter().any(|column| {
        column
            .column_type
            .as_ref()
            .is_some_and(|column_type| enum_names.contains(column_type))
    });
    enum_typed.then_some(PlainModelBlocker::EnumColumns)
}

pub(crate) fn plain_model_facts(model: PlainModel) -> CompiledModelFacts {
    CompiledModelFacts {
        schema: model.schema,
        name: model.name,
        relative_path: model.relative_path,
        query_sql: model.query_sql,
        authored_query_sql: model.authored_query_sql,
        authored_sql: model.authored_sql,
        config: model.config,
        references: model.references,
        enum_columns: Vec::new(),
        enum_declarations: model.enum_declarations,
        constant_declarations: model.constant_declarations,
        analysis: None,
    }
}
