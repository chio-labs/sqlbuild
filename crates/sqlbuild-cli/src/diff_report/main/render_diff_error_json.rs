//! The machine-readable document of an incomplete or failed diff.

use sqlbuild_core::json::errors::JsonEmitError;
use sqlbuild_core::json::main::dumps::dumps;
use sqlbuild_core::json::models::{JsonDialect, JsonValue, StdlibJsonOptions};

use crate::diff_report::_helpers::payload::{integer, object, text};
use crate::diff_report::models::DiffErrorFacts;

/// The error document text, without a trailing newline.
pub fn render_diff_error_json(facts: &DiffErrorFacts) -> Result<String, JsonEmitError> {
    let mut error: Vec<(&str, JsonValue)> = vec![
        ("code", text(&facts.code)),
        ("message", text(&facts.message)),
    ];
    if let Some(help) = &facts.help {
        error.push(("help", text(help)));
    }
    let mut entries: Vec<(&str, JsonValue)> = vec![
        ("schema_version", integer(1)),
        ("status", text(&facts.status)),
        ("outcome", text(&facts.status)),
        ("error", object(error)),
        ("models", JsonValue::Array(Vec::new())),
        ("query_comparisons", JsonValue::Array(Vec::new())),
    ];
    if let Some(size_guard) = &facts.size_guard {
        entries.push(("size_guard", size_guard.clone()));
    }
    let mut settings: StdlibJsonOptions = StdlibJsonOptions::new(Some(2));
    settings.sort_keys = true;
    dumps(&object(entries), &JsonDialect::Stdlib(settings))
}
