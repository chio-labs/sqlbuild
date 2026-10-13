//! Sizes, payloads and replacement commands of the full-diff size guard.

use sqlbuild_core::json::models::JsonValue;

use crate::diff_report::_helpers::numbers::grouped;
use crate::diff_report::_helpers::payload::{integer, object, text};
use crate::diff_report::_helpers::shell_words::quote;
use crate::diff_report::constants::BOUNDED_WINDOW_PLACEHOLDER;
use crate::diff_report::models::{DiffRequestFacts, FullDiffSideFacts};

pub(crate) fn side_text(side: &FullDiffSideFacts) -> String {
    let limit: String = side
        .max_rows
        .map_or_else(|| "unlimited".to_owned(), grouped);
    let size: String = match (side.row_count, &side.detail) {
        (Some(rows), _) => format!("{} rows", grouped(rows)),
        (None, Some(detail)) => format!("size unknown: {detail}"),
        (None, None) => "size unknown".to_owned(),
    };
    format!("{} {size}, limit {limit}", side.target)
}

pub(crate) fn optional_integer(value: Option<i64>) -> JsonValue {
    value.map_or(JsonValue::Null, integer)
}

pub(crate) fn side_payload(side: &FullDiffSideFacts) -> JsonValue {
    object(vec![
        ("target", text(&side.target)),
        ("relation", text(&side.relation)),
        ("row_count", optional_integer(side.row_count)),
        ("max_full_rows", optional_integer(side.max_rows)),
        ("exceeds_limit", JsonValue::Bool(side.exceeds_limit)),
        (
            "detail",
            side.detail.as_deref().map_or(JsonValue::Null, text),
        ),
    ])
}

pub(crate) fn scope_arguments(request: &DiffRequestFacts) -> Vec<String> {
    let mut arguments: Vec<String> = Vec::new();
    for (flag, values) in [
        ("--select", &request.select),
        ("--exclude", &request.exclude),
        ("--key", &request.unique_key_override),
    ] {
        if !values.is_empty() {
            arguments.push(flag.to_owned());
            arguments.extend(values.iter().cloned());
        }
    }
    if request.unkeyed {
        arguments.push("--unkeyed".to_owned());
    }
    if !request.excluded_columns_override.is_empty() {
        arguments.push("--exclude-column".to_owned());
        arguments.extend(request.excluded_columns_override.iter().cloned());
    }
    for tolerance in &request.tolerance_overrides {
        arguments.extend(["--tolerance".to_owned(), tolerance.clone()]);
    }
    if let Some(variables) = &request.cli_vars_json {
        arguments.extend(["--vars".to_owned(), variables.clone()]);
    }
    arguments
}

pub(crate) fn command(prefix: &[String], mode: &[&str], scope: &[String]) -> String {
    prefix
        .iter()
        .map(String::as_str)
        .chain(mode.iter().copied())
        .chain(scope.iter().map(String::as_str))
        .map(|part| {
            if part == BOUNDED_WINDOW_PLACEHOLDER {
                part.to_owned()
            } else {
                quote(part)
            }
        })
        .collect::<Vec<String>>()
        .join(" ")
}
