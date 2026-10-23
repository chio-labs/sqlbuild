//! JSON values of refactoring plans.

use sqlbuild_core::json::models::{JsonInteger, JsonValue};

use crate::refactor_command::_helpers::output_text::sorted_edits;
use crate::refactor_command::models::RefactorDiagnostic;
use crate::refactoring::models::{FileChange, ManualLocation, RefactorOperation, RefactorPlan};

pub(crate) fn text(value: &str) -> JsonValue {
    JsonValue::String(value.to_owned())
}

pub(crate) fn optional_text(value: Option<&str>) -> JsonValue {
    value.map_or(JsonValue::Null, text)
}

pub(crate) fn integer(value: Option<i64>) -> JsonValue {
    value.map_or(JsonValue::Null, |value| {
        JsonValue::Integer(JsonInteger::from(value))
    })
}

pub(crate) fn count(value: usize) -> JsonValue {
    JsonValue::Integer(JsonInteger::from(u64::try_from(value).unwrap_or(u64::MAX)))
}

fn optional_count(value: Option<usize>) -> JsonValue {
    value.map_or(JsonValue::Null, count)
}

pub(crate) fn object(entries: Vec<(&str, JsonValue)>) -> JsonValue {
    JsonValue::Object(
        entries
            .into_iter()
            .map(|(name, value)| (name.to_owned(), value))
            .collect(),
    )
}

pub(crate) fn file(change: &FileChange) -> JsonValue {
    object(vec![
        ("path", text(&change.path)),
        (
            "from_path",
            optional_text(change.moved().then_some(change.original_path.as_str())),
        ),
        (
            "edits",
            JsonValue::Array(
                sorted_edits(change)
                    .into_iter()
                    .map(|edit| {
                        object(vec![
                            ("line", count(edit.line)),
                            ("column", count(edit.column)),
                            ("kind", text(edit.kind.value())),
                            ("before", text(&edit.before)),
                            ("after", text(&edit.after)),
                        ])
                    })
                    .collect(),
            ),
        ),
    ])
}

pub(crate) fn location(item: &ManualLocation) -> JsonValue {
    object(vec![
        ("path", text(&item.path)),
        ("line", optional_count(item.line)),
        ("column", optional_count(item.column)),
        ("reason", text(&item.reason)),
    ])
}

/// Each diagnostic as `{code, message, path, line}`.
pub(crate) fn diagnostic_array(diagnostics: &[RefactorDiagnostic]) -> JsonValue {
    JsonValue::Array(
        diagnostics
            .iter()
            .map(|diagnostic| {
                object(vec![
                    ("code", text(&diagnostic.code)),
                    ("message", text(&diagnostic.message)),
                    ("path", optional_text(diagnostic.path.as_deref())),
                    ("line", integer(diagnostic.line)),
                ])
            })
            .collect(),
    )
}

/// Every request of a batch as `{"target", "new_name" for renames, "destination"}`.
pub(crate) fn batch_moves(plan: &RefactorPlan) -> JsonValue {
    JsonValue::Array(
        plan.batch
            .iter()
            .map(|request| {
                let mut entries: Vec<(&str, JsonValue)> =
                    vec![("target", text(&format!("model:{}", request.model_name)))];
                if request.operation != RefactorOperation::MoveModel {
                    entries.push(("new_name", text(&request.new_name)));
                }
                entries.push(("destination", optional_text(request.destination.as_deref())));
                object(entries)
            })
            .collect(),
    )
}

pub(crate) fn operation_value(plan: &RefactorPlan) -> &'static str {
    match plan.request.operation {
        RefactorOperation::RenameModel => "rename_model",
        RefactorOperation::MoveModel => "move_model",
        RefactorOperation::RenameColumn => "rename_column",
    }
}
