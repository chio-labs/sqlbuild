//! The JSON error document of `sqb rename` and `sqb mv` when the project does not compile.

use sqlbuild_core::json::errors::JsonEmitError;
use sqlbuild_core::json::main::dumps::dumps;
use sqlbuild_core::json::models::{JsonDialect, JsonValue, StdlibJsonOptions};

use crate::refactor_command::_helpers::json::{diagnostic_array, object, text};
use crate::refactor_command::constants::{PROJECT_FAILED_CODE, PROJECT_FAILED_STATUS};
use crate::refactor_command::models::RefactorDiagnostic;

/// `{"status", "error": {code, message, help}, "compile": {ok, errors}}` with a trailing newline.
pub fn render_project_failure_json(
    (message, help): (&str, &str),
    diagnostics: &[RefactorDiagnostic],
) -> Result<String, JsonEmitError> {
    let payload: JsonValue = object(vec![
        ("status", text(PROJECT_FAILED_STATUS)),
        (
            "error",
            object(vec![
                ("code", text(PROJECT_FAILED_CODE)),
                ("message", text(message)),
                ("help", text(help)),
            ]),
        ),
        (
            "compile",
            object(vec![
                ("ok", JsonValue::Bool(false)),
                ("errors", diagnostic_array(diagnostics)),
            ]),
        ),
    ]);
    let dialect: JsonDialect = JsonDialect::Stdlib(StdlibJsonOptions::new(Some(2)));
    Ok(format!("{}\n", dumps(&payload, &dialect)?))
}
