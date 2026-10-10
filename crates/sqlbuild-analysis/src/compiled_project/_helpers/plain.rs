//! Deciding whether the native loop finishes a model, and finishing it.

use crate::compiled_project::constants::{
    CALLBACK_CONFIG_KEYS, DESCRIPTION_KEY, HEADER_METADATA_KEYS, MACRO_TOKEN,
};
use crate::compiled_project::models::{
    AnalysisOverride, CompiledModelFacts, DescriptionShape, ModelSchemaFact, PlainModel,
    PlainModelBlocker, PlainModelCheck,
};

pub(crate) fn plain_model_blocker(check: &PlainModelCheck) -> Option<PlainModelBlocker> {
    let Some(sql) = &check.interpolated_sql else {
        return Some(PlainModelBlocker::Interpolation);
    };
    if check.settings.legacy_schema_files {
        return Some(PlainModelBlocker::LegacySchemaFiles);
    }
    if !check.settings.defer_sql_validation {
        return Some(PlainModelBlocker::ImmediateSqlValidation);
    }
    if !analysis_enabled(check) {
        return Some(PlainModelBlocker::SqlAnalysisDisabled);
    }
    if check.has_declaration_references {
        return Some(PlainModelBlocker::Declarations);
    }
    if sql.contains(MACRO_TOKEN) {
        return Some(PlainModelBlocker::Macros);
    }
    if check
        .config_keys
        .iter()
        .any(|key| CALLBACK_CONFIG_KEYS.contains(&key.as_str()))
    {
        return Some(PlainModelBlocker::CallbackConfig);
    }
    let metadata_beyond_description: bool = check
        .config_keys
        .iter()
        .any(|key| key != DESCRIPTION_KEY && HEADER_METADATA_KEYS.contains(&key.as_str()));
    if metadata_beyond_description || check.description == DescriptionShape::Invalid {
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

/// The retained facts; a description alone attaches an empty schema entry, as the header does.
pub(crate) fn plain_model_facts(model: PlainModel) -> CompiledModelFacts {
    CompiledModelFacts {
        schema: model
            .description
            .as_ref()
            .map(|_| ModelSchemaFact::default()),
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
