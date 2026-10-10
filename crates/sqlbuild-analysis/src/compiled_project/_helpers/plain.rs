//! The model loop's ordered decisions and the facts it retains for a finished model.

use crate::compiled_project::constants::{
    AUDIT_FACTORIES_KEY, DYNAMIC_COLUMNS_KEY, MACRO_TOKEN, MODEL_SCHEMA_KEY,
};
use crate::compiled_project::models::{
    AnalysisGate, AnalysisOverride, AttachmentFeature, CompiledModelFacts, HeaderColumnShape,
    ModelLoopSettings, PlainModel,
};

/// The attachment's gate: project switches first, so an override is only read when they allow.
pub(crate) fn analysis_gate(
    settings: ModelLoopSettings,
    analysis_override: AnalysisOverride,
) -> AnalysisGate {
    if !settings.sql_analysis || settings.no_sql_validation {
        return AnalysisGate::Disabled;
    }
    match analysis_override {
        AnalysisOverride::Inherit | AnalysisOverride::Enabled => AnalysisGate::Enabled,
        AnalysisOverride::Disabled => AnalysisGate::Disabled,
        AnalysisOverride::Conflict => AnalysisGate::Conflict,
    }
}

/// The header feature among `keys` the attachment still finishes, earliest first.
pub(crate) fn header_attachment_feature(keys: &[String]) -> Option<AttachmentFeature> {
    let has = |wanted: &str| keys.iter().any(|key| key == wanted);
    if has(MODEL_SCHEMA_KEY) {
        return Some(AttachmentFeature::ModelSchema);
    }
    if has(DYNAMIC_COLUMNS_KEY) {
        return Some(AttachmentFeature::DynamicColumns);
    }
    has(AUDIT_FACTORIES_KEY).then_some(AttachmentFeature::AuditFactories)
}

/// Whether declaration-expanded SQL still calls macros.
pub(crate) fn calls_macros(sql: &str) -> bool {
    sql.contains(MACRO_TOKEN)
}

/// Whether any column is typed as a visible enum.
pub(crate) fn enum_typed_columns(columns: &[HeaderColumnShape], enum_names: &[String]) -> bool {
    columns.iter().any(|column| {
        column
            .column_type
            .as_ref()
            .is_some_and(|column_type| enum_names.contains(column_type))
    })
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
