//! The JSON payload of `sqb check`.

use crate::check_command::_helpers::json_payload::{check, integer, object, text};
use crate::check_command::models::{CheckResultText, CheckStatus};
use crate::json::errors::JsonEmitError;
use crate::json::main::dumps::dumps;
use crate::json::models::{JsonDialect, JsonValue, StdlibJsonOptions};

/// Status, counts and checks as `json.dumps(..., indent=2)` with a trailing newline.
pub fn check_json(results: &[CheckResultText]) -> Result<String, JsonEmitError> {
    let count = |status: CheckStatus| {
        integer(
            results
                .iter()
                .filter(|result| result.status == status)
                .count(),
        )
    };
    let failed: bool = results
        .iter()
        .any(|result| result.status == CheckStatus::Fail);
    let payload: JsonValue = object(vec![
        ("version", integer(1)),
        ("command", text(Some("check"))),
        (
            "status",
            text(Some(if failed { "failed" } else { "success" })),
        ),
        (
            "summary",
            object(vec![
                ("pass_count", count(CheckStatus::Pass)),
                ("warn_count", count(CheckStatus::Warn)),
                ("fail_count", count(CheckStatus::Fail)),
                ("total_count", integer(results.len())),
            ]),
        ),
        (
            "checks",
            JsonValue::Array(results.iter().map(check).collect()),
        ),
    ]);
    Ok(format!(
        "{}\n",
        dumps(
            &payload,
            &JsonDialect::Stdlib(StdlibJsonOptions::new(Some(2)))
        )?
    ))
}
