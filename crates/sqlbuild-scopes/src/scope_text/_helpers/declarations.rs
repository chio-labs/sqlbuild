//! Declaration rows, their details, explanations and move previews.

use std::collections::HashSet;

use sqlbuild_core::cli_text::models::CliStyle;
use sqlbuild_core::json::models::JsonValue;

use crate::scope_report::models::{DeclarationReport, MovePreview};
use crate::scope_text::_helpers::layout::{
    connector, display_path, field, header, none_line, plain_header, scope_label,
};
use crate::scope_text::constants::{NONE_TEXT, PATH_NONE, UNUSED_MARKER, USED_MARKER};
use crate::scope_text::models::ScopeTextRequest;
use crate::scope_text::types::Styler;

/// How one block of declaration rows is styled and how much it shows.
pub(crate) struct DeclarationStyle<'a> {
    pub(crate) used: &'a HashSet<String>,
    pub(crate) used_marker: Option<Styler<'a>>,
    pub(crate) name: Option<Styler<'a>>,
    /// Whether to show details; `None` follows `--verbose`.
    pub(crate) detailed: Option<bool>,
}

impl<'a> DeclarationStyle<'a> {
    /// Rows marking `used` declarations, in the default styles.
    pub(crate) fn marking(used: &'a HashSet<String>) -> Self {
        Self {
            used,
            used_marker: None,
            name: None,
            detailed: None,
        }
    }
}

fn integer_text(value: &JsonValue) -> Option<String> {
    match value {
        JsonValue::Integer(integer) => Some(integer.as_str().to_owned()),
        JsonValue::Bool(flag) => Some(if *flag { "True" } else { "False" }.to_owned()),
        _ => None,
    }
}

fn string_text(value: &JsonValue) -> Option<&str> {
    match value {
        JsonValue::String(text) => Some(text),
        _ => None,
    }
}

/// The metadata facts a detailed row lists.
fn metadata_parts(declaration: &DeclarationReport) -> Vec<String> {
    let value = |key: &str| -> Option<&JsonValue> {
        declaration
            .metadata
            .iter()
            .rev()
            .find(|(name, _)| name == key)
            .map(|(_, value)| value)
    };
    let mut parts: Vec<String> = Vec::new();
    if let Some(JsonValue::Array(parameters)) = value("parameters") {
        parts.push(format!("params {}", parameters.len()));
    }
    if let Some(members) = value("member_count").and_then(integer_text) {
        parts.push(format!("members {members}"));
    }
    if let Some(scalar_type) = value("scalar_type").and_then(string_text) {
        parts.push(format!("type {scalar_type}"));
    }
    if let Some(logical_type) = value("logical_type").and_then(string_text) {
        parts.push(format!("type {logical_type}"));
    }
    if let Some(collection) = value("collection_kind").and_then(string_text) {
        parts.push(match value("item_count").and_then(integer_text) {
            Some(count) => format!("{collection} {count}"),
            None => collection.to_owned(),
        });
    }
    if let Some(role_root) = value("role_root").and_then(string_text) {
        parts.push(format!("role {role_root}"));
    }
    if let Some(bucket_path) = value("bucket_path").and_then(string_text) {
        parts.push(format!("bucket {bucket_path} (navigation only)"));
    }
    parts
}

fn declaration_details(declaration: &DeclarationReport) -> Vec<String> {
    let mut details: Vec<String> = vec![declaration.kind.clone(), scope_label(&declaration.scope)];
    if let Some(visibility) = &declaration.visibility {
        details.push(match &visibility.through {
            Some(through) => format!("{} through {through}", visibility.reason),
            None => visibility.reason.clone(),
        });
    }
    if let Some(reason) = &declaration.inaccessible_reason {
        details.push(reason.clone());
    }
    details.extend(metadata_parts(declaration));
    details
}

/// One row per declaration with its used marker, details and definition location.
pub(crate) fn declaration_lines(
    (style, request): (CliStyle, &ScopeTextRequest),
    declarations: &[DeclarationReport],
    options: &DeclarationStyle<'_>,
) -> Vec<String> {
    if declarations.is_empty() {
        return vec![none_line(style)];
    }
    let show_details: bool = options.detailed.unwrap_or(request.verbose);
    let mut lines: Vec<String> = Vec::new();
    for (index, declaration) in declarations.iter().enumerate() {
        let marker: String = if options.used.contains(&declaration.identity) {
            options
                .used_marker
                .map_or_else(|| style.success(USED_MARKER), |styler| styler(USED_MARKER))
        } else {
            style.muted(UNUSED_MARKER)
        };
        let name: String = options.name.map_or_else(
            || style.object_name(&declaration.identity),
            |styler| styler(&declaration.identity),
        );
        let mut line: String = format!(
            "  {} {marker} {name}",
            connector(style, index == declarations.len() - 1)
        );
        if show_details {
            let details: String = declaration_details(declaration).join("; ");
            line.push_str(&format!("  {}", style.muted(&format!("[{details}]"))));
        }
        if request.paths != PATH_NONE {
            let location = &declaration.definition;
            let position: String = if show_details {
                format!("{}:{}", location.line, location.column)
            } else {
                location.line.to_string()
            };
            let path: String = display_path(Some(&location.path), &request.paths);
            line.push_str(&format!("  {}", style.muted(&format!("{path}:{position}"))));
        }
        lines.push(line);
    }
    lines
}

/// One declaration group of a move preview and how it is styled.
struct MoveSection<'a> {
    title: &'a str,
    values: &'a [DeclarationReport],
    optional: bool,
    warned: bool,
    used_marker: Option<Styler<'a>>,
    name: Option<Styler<'a>>,
}

impl<'a> MoveSection<'a> {
    fn plain(title: &'a str, values: &'a [DeclarationReport], optional: bool) -> Self {
        Self {
            title,
            values,
            optional,
            warned: false,
            used_marker: None,
            name: None,
        }
    }
}

fn joined_or_none(style: CliStyle, values: &[String]) -> String {
    if values.is_empty() {
        return style.muted(NONE_TEXT);
    }
    values.join(", ")
}

fn text_or_none(style: CliStyle, value: Option<&str>) -> String {
    value.map_or_else(|| style.muted(NONE_TEXT), str::to_owned)
}

/// The explained declaration's detailed row followed by its ownership facts.
pub(crate) fn explanation_lines(
    (style, request): (CliStyle, &ScopeTextRequest),
    declaration: &DeclarationReport,
    used: &HashSet<String>,
) -> Vec<String> {
    let mut lines: Vec<String> = declaration_lines(
        (style, request),
        std::slice::from_ref(declaration),
        &DeclarationStyle {
            detailed: Some(true),
            ..DeclarationStyle::marking(used)
        },
    );
    let required_scope: Option<String> = declaration.required_scope.as_deref().map(scope_label);
    let facts: [(&str, String); 8] = [
        ("Owner", text_or_none(style, declaration.owner.as_deref())),
        (
            "Owning path",
            text_or_none(style, declaration.owning_path.as_deref()),
        ),
        ("Consumers", joined_or_none(style, &declaration.consumers)),
        (
            "Dependencies",
            joined_or_none(style, &declaration.dependencies),
        ),
        ("Grants", joined_or_none(style, &declaration.grants)),
        (
            "Required scope",
            text_or_none(style, required_scope.as_deref()),
        ),
        (
            "Required path",
            text_or_none(style, declaration.required_path.as_deref()),
        ),
        (
            "Promotion impact",
            joined_or_none(style, &declaration.promotion_impact),
        ),
    ];
    for (label, rendered) in facts {
        lines.push(format!(
            "     {} {rendered}",
            style.muted(&format!("{label}:"))
        ));
    }
    lines
}

/// The move preview: destination facts, then retained, gained and lost declarations.
pub(crate) fn move_lines(
    (style, request): (CliStyle, &ScopeTextRequest),
    preview: &MovePreview,
    used: &HashSet<String>,
) -> Vec<String> {
    let mut lines: Vec<String> = vec![
        style.section("Move preview"),
        field(style, "Resource", &preview.resource),
        field(
            style,
            "Destination",
            &display_path(Some(&preview.destination), &request.paths),
        ),
        field(
            style,
            "Ownership root",
            &display_path(preview.new_ownership_root.as_deref(), &request.paths),
        ),
    ];
    let lost_warning: bool = !preview.lost.is_empty();
    let warning_strong = |text: &str| style.warning_strong(text);
    let warning = |text: &str| style.warning(text);
    let error = |text: &str| style.error(text);
    let success = |text: &str| style.success(text);
    let sections: [MoveSection<'_>; 5] = [
        MoveSection::plain("Retained", &preview.retained, false),
        MoveSection {
            name: Some(&success),
            ..MoveSection::plain("Gained", &preview.gained, false)
        },
        MoveSection {
            warned: lost_warning,
            used_marker: Some(&error),
            ..MoveSection::plain("Lost", &preview.lost, false)
        },
        MoveSection::plain("Private retained", &preview.private_retained, true),
        MoveSection::plain(
            "Relationship retained",
            &preview.relationship_retained,
            true,
        ),
    ];
    for MoveSection {
        title,
        values,
        optional,
        warned,
        used_marker,
        name,
    } in sections
    {
        if optional && !request.verbose && values.is_empty() {
            continue;
        }
        let count: String = format!("({})", values.len());
        let section_header: String = if warned {
            header(title, &count, (&warning_strong, &warning))
        } else {
            plain_header(style, title, &count)
        };
        lines.push(format!("  {section_header}"));
        let rows: Vec<String> = declaration_lines(
            (style, request),
            values,
            &DeclarationStyle {
                used_marker,
                name,
                ..DeclarationStyle::marking(used)
            },
        );
        lines.extend(rows.into_iter().map(|row| format!("  {row}")));
    }
    let invalidated: &[String] = &preview.invalidated_usages;
    let count: String = format!("({})", invalidated.len());
    let invalidated_header: String = if invalidated.is_empty() {
        plain_header(style, "Invalidated usages", &count)
    } else {
        header(
            "Invalidated usages",
            &count,
            (&|text: &str| style.error_strong(text), &error),
        )
    };
    lines.push(format!("  {invalidated_header}"));
    for identity in invalidated {
        lines.push(format!("    {}", style.error(&format!("- {identity}"))));
    }
    if invalidated.is_empty() {
        lines.push(format!("    {}", style.muted(NONE_TEXT)));
    }
    lines
}
