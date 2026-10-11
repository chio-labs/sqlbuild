//! JSON objects of report results, as `serialize_result` walks the report dataclasses.

use sqlbuild_core::json::main::dumps::dumps;
use sqlbuild_core::json::models::{JsonDialect, JsonValue, StdlibJsonOptions};

use crate::scope_report::_helpers::declarations::{integer, optional_text, text, texts};
use crate::scope_report::_helpers::paths::safe_scope_path;
use crate::scope_report::constants::ESCAPE_CHARACTER;
use crate::scope_report::models::{
    DeclarationReport, DiagnosticFacts, Explanation, MovePreview, Provenance, ReportDiagnostic,
    ReportFailure, ReportFilters, ResourceReport, ScopeChainEntry, ScopeFolder, ScopeSection,
};

/// One JSON object from its fields in order.
pub(crate) fn object(fields: Vec<(&str, JsonValue)>) -> JsonValue {
    JsonValue::Object(
        fields
            .into_iter()
            .map(|(key, value)| (key.to_owned(), value))
            .collect(),
    )
}

/// `json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))`.
pub(crate) fn canonical_json(value: &JsonValue) -> Result<String, ReportFailure> {
    let mut options: StdlibJsonOptions = StdlibJsonOptions::new(None).with_separators(",", ":");
    options.sort_keys = true;
    dumps(value, &JsonDialect::Stdlib(options))
        .map_err(|error| ReportFailure::Serialization(format!("{error:?}")))
}

fn optional_integer(value: Option<i64>) -> JsonValue {
    value.map_or(JsonValue::Null, integer)
}

/// `diagnostic_projection`.
pub(crate) fn diagnostic_json(diagnostic: &DiagnosticFacts) -> JsonValue {
    object(vec![
        ("code", text(&diagnostic.code)),
        (
            "message",
            JsonValue::String(diagnostic.message.replace(ESCAPE_CHARACTER, "")),
        ),
        ("severity", text(&diagnostic.severity)),
        (
            "path",
            diagnostic
                .path
                .as_deref()
                .map_or(JsonValue::Null, |path| text(&safe_scope_path(path))),
        ),
        ("line", optional_integer(diagnostic.line)),
        ("column", optional_integer(diagnostic.column)),
        (
            "declaration",
            optional_text(diagnostic.declaration.as_deref()),
        ),
        ("resource", optional_text(diagnostic.resource.as_deref())),
    ])
}

pub(crate) fn diagnostics_json(
    diagnostics: &[ReportDiagnostic],
) -> Result<JsonValue, ReportFailure> {
    let mut values: Vec<JsonValue> = Vec::new();
    for diagnostic in diagnostics {
        match diagnostic {
            ReportDiagnostic::Raised(facts) => values.push(diagnostic_json(facts)),
            ReportDiagnostic::Index(_) => {
                return Err(ReportFailure::Serialization(
                    "an index diagnostic reached serialization without its facts".to_owned(),
                ));
            }
        }
    }
    Ok(JsonValue::Array(values))
}

fn provenance_json(provenance: Option<&Provenance>) -> JsonValue {
    provenance.map_or(JsonValue::Null, |provenance| {
        object(vec![
            ("reason", text(&provenance.reason)),
            ("through", optional_text(provenance.through.as_deref())),
        ])
    })
}

pub(crate) fn declaration_json(report: &DeclarationReport) -> JsonValue {
    object(vec![
        ("identity", text(&report.identity)),
        ("kind", text(&report.kind)),
        ("name", text(&report.name)),
        ("owner", optional_text(report.owner.as_deref())),
        (
            "definition",
            object(vec![
                ("path", text(&report.definition.path)),
                ("line", integer(report.definition.line)),
                ("column", integer(report.definition.column)),
            ]),
        ),
        ("scope", text(&report.scope)),
        ("owning_path", optional_text(report.owning_path.as_deref())),
        ("visibility", provenance_json(report.visibility.as_ref())),
        (
            "inaccessible_reason",
            optional_text(report.inaccessible_reason.as_deref()),
        ),
        ("metadata", JsonValue::Object(report.metadata.clone())),
        ("consumers", texts(&report.consumers)),
        ("dependencies", texts(&report.dependencies)),
        ("grants", texts(&report.grants)),
        (
            "required_scope",
            optional_text(report.required_scope.as_deref()),
        ),
        (
            "required_path",
            optional_text(report.required_path.as_deref()),
        ),
        ("promotion_impact", texts(&report.promotion_impact)),
    ])
}

pub(crate) fn declarations_json(reports: &[DeclarationReport]) -> JsonValue {
    JsonValue::Array(reports.iter().map(declaration_json).collect())
}

pub(crate) fn section_json(section: &ScopeSection) -> JsonValue {
    object(vec![
        ("name", text(&section.name)),
        ("total", integer(section.total)),
        ("returned", integer(section.returned)),
        ("collapsed", JsonValue::Bool(section.collapsed)),
        ("collapsed_count", integer(section.collapsed_count)),
        ("truncated", JsonValue::Bool(section.truncated)),
        ("complete", JsonValue::Bool(section.complete)),
        ("next_cursor", optional_text(section.next_cursor.as_deref())),
        ("cursor", optional_text(section.cursor.as_deref())),
        ("page_size", integer(section.page_size)),
    ])
}

pub(crate) fn resource_json(resource: &ResourceReport) -> JsonValue {
    object(vec![
        ("target", text(&resource.target)),
        ("identity", optional_text(resource.identity.as_deref())),
        ("path", optional_text(resource.path.as_deref())),
        ("prospective", JsonValue::Bool(resource.prospective)),
        ("directory", JsonValue::Bool(resource.directory)),
        ("duplicate_count", integer(resource.duplicate_count)),
    ])
}

pub(crate) fn chain_json(entries: &[ScopeChainEntry]) -> JsonValue {
    JsonValue::Array(
        entries
            .iter()
            .map(|entry| {
                object(vec![
                    ("kind", text(&entry.kind)),
                    ("path", text(&entry.path)),
                    ("declaration_count", integer(entry.declaration_count)),
                ])
            })
            .collect(),
    )
}

pub(crate) fn filters_json(filters: &ReportFilters) -> JsonValue {
    object(vec![
        ("sections", texts(&filters.sections)),
        ("include_nearby", JsonValue::Bool(filters.include_nearby)),
        (
            "defined_under",
            optional_text(filters.defined_under.as_deref()),
        ),
        ("kinds", texts(&filters.kinds)),
        ("glob", optional_text(filters.glob.as_deref())),
        ("used_only", JsonValue::Bool(filters.used_only)),
        ("dependency_depth", integer(filters.dependency_depth)),
        ("sort", text(&filters.sort)),
        ("cursor", optional_text(filters.cursor.as_deref())),
        ("page_size", integer(filters.page_size)),
        ("nearby_depth", integer(filters.nearby_depth)),
        ("globals", text(&filters.globals)),
    ])
}

pub(crate) fn explanation_json(explanation: Option<&Explanation>) -> JsonValue {
    explanation.map_or(JsonValue::Null, |explanation| {
        object(vec![
            (
                "declaration",
                explanation
                    .declaration
                    .as_ref()
                    .map_or(JsonValue::Null, declaration_json),
            ),
            ("complete", JsonValue::Bool(explanation.complete)),
        ])
    })
}

pub(crate) fn move_json(preview: Option<&MovePreview>) -> JsonValue {
    preview.map_or(JsonValue::Null, |preview| {
        object(vec![
            ("resource", text(&preview.resource)),
            ("destination", text(&preview.destination)),
            (
                "new_ownership_root",
                optional_text(preview.new_ownership_root.as_deref()),
            ),
            ("retained", declarations_json(&preview.retained)),
            ("gained", declarations_json(&preview.gained)),
            ("lost", declarations_json(&preview.lost)),
            ("invalidated_usages", texts(&preview.invalidated_usages)),
            (
                "private_retained",
                declarations_json(&preview.private_retained),
            ),
            (
                "relationship_retained",
                declarations_json(&preview.relationship_retained),
            ),
            ("complete", JsonValue::Bool(preview.complete)),
        ])
    })
}

pub(crate) fn folder_json(folder: &ScopeFolder) -> JsonValue {
    object(vec![
        ("path", text(&folder.path)),
        ("name", text(&folder.name)),
        ("descendant_count", integer(folder.descendant_count)),
        ("child_count", integer(folder.child_count)),
        ("used_count", integer(folder.used_count)),
        (
            "kind_counts",
            JsonValue::Object(
                folder
                    .kind_counts
                    .iter()
                    .map(|(kind, count)| (kind.clone(), integer(*count)))
                    .collect(),
            ),
        ),
    ])
}
