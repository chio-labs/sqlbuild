//! The JSON output of `sqb rename` and `sqb mv`.

use sqlbuild_core::json::errors::JsonEmitError;
use sqlbuild_core::json::main::dumps::dumps;
use sqlbuild_core::json::models::{JsonDialect, JsonValue, StdlibJsonOptions};

use crate::refactor_command::_helpers::json::{
    count, file, integer, location, object, operation_value, optional_text, text,
};
use crate::refactor_command::_helpers::output_text::refactor_target;
use crate::refactor_command::models::{RefactorDiagnostic, RefactorStatus};
use crate::refactoring::models::RefactorPlan;

/// The same facts as the text output, as stable JSON with a trailing newline.
pub fn render_refactor_json(
    plan: &RefactorPlan,
    status: RefactorStatus,
    diagnostics: &[RefactorDiagnostic],
) -> Result<String, JsonEmitError> {
    let request = &plan.request;
    let changed: usize = if status == RefactorStatus::Applied {
        plan.changes.len()
    } else {
        0
    };
    let payload: JsonValue = object(vec![
        ("operation", text(operation_value(plan))),
        ("target", text(&refactor_target(plan))),
        ("new_name", text(&request.new_name)),
        ("destination", optional_text(request.destination.as_deref())),
        ("cascade", JsonValue::Bool(request.cascade)),
        ("status", text(status.value())),
        ("files_changed", count(changed)),
        (
            "files",
            JsonValue::Array(plan.changes.iter().map(file).collect()),
        ),
        (
            "migrations",
            JsonValue::Array(
                plan.migrations
                    .iter()
                    .map(|migration| {
                        object(vec![
                            ("model", text(&migration.model_name)),
                            ("declaration", text(&migration.declaration)),
                            ("reason", text(&migration.reason)),
                        ])
                    })
                    .collect(),
            ),
        ),
        (
            "renamed_columns",
            JsonValue::Array(
                plan.renamed_columns
                    .iter()
                    .map(|(model, old, new)| {
                        object(vec![
                            ("model", text(model)),
                            ("from", text(old)),
                            ("to", text(new)),
                        ])
                    })
                    .collect(),
            ),
        ),
        (
            "manual",
            JsonValue::Array(plan.manual.iter().map(location).collect()),
        ),
        (
            "blocking",
            JsonValue::Array(plan.blocking.iter().map(location).collect()),
        ),
        (
            "compile",
            object(vec![
                ("ok", JsonValue::Bool(diagnostics.is_empty())),
                (
                    "errors",
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
                    ),
                ),
            ]),
        ),
    ]);
    let dialect: JsonDialect = JsonDialect::Stdlib(StdlibJsonOptions::new(Some(2)));
    Ok(format!("{}\n", dumps(&payload, &dialect)?))
}
