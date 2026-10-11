//! `serialize_scope_report`: deterministic schema-version-two ASCII JSON of a query result.

use sqlbuild_core::json::models::JsonValue;

use crate::scope_report::_helpers::declarations::integer;
use crate::scope_report::_helpers::json::{
    canonical_json, chain_json, declarations_json, diagnostics_json, explanation_json,
    filters_json, folder_json, move_json, object, resource_json, section_json,
};
use crate::scope_report::constants::RESULT_SCHEMA_VERSION;
use crate::scope_report::models::{ReportFailure, ScopeResult};

/// The result's JSON text with a trailing newline.
pub fn serialize_scope_result(result: &ScopeResult) -> Result<String, ReportFailure> {
    let schema: (&str, JsonValue) = ("schema_version", integer(RESULT_SCHEMA_VERSION));
    let payload: JsonValue = match result {
        ScopeResult::Report(report) => object(vec![
            schema,
            ("resource", resource_json(&report.resource)),
            ("scope_chain", chain_json(&report.scope_chain)),
            ("available", declarations_json(&report.available)),
            ("used", declarations_json(&report.used)),
            (
                "relationship_scope",
                declarations_json(&report.relationship_scope),
            ),
            (
                "nearby_unavailable",
                declarations_json(&report.nearby_unavailable),
            ),
            ("filters", filters_json(&report.filters)),
            (
                "sections",
                JsonValue::Array(report.sections.iter().map(section_json).collect()),
            ),
            ("explanation", explanation_json(report.explanation.as_ref())),
            ("move_preview", move_json(report.move_preview.as_ref())),
            ("diagnostics", diagnostics_json(&report.diagnostics)?),
            ("complete", JsonValue::Bool(report.complete)),
        ]),
        ScopeResult::Browse(browse) => object(vec![
            schema,
            ("folder", JsonValue::String(browse.folder.clone())),
            (
                "folders",
                JsonValue::Array(browse.folders.iter().map(folder_json).collect()),
            ),
            ("diagnostics", diagnostics_json(&browse.diagnostics)?),
            ("complete", JsonValue::Bool(browse.complete)),
        ]),
        ScopeResult::List(list) => object(vec![
            schema,
            ("folder", JsonValue::String(list.folder.clone())),
            ("declarations", declarations_json(&list.declarations)),
            ("section", section_json(&list.section)),
            ("diagnostics", diagnostics_json(&list.diagnostics)?),
        ]),
    };
    Ok(canonical_json(&payload)? + "\n")
}
