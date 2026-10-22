//! `sqb janitor --json`.

use crate::janitor_text::_helpers::plan_json::{plan_payload, run_payload};
use crate::janitor_text::models::{JanitorOutcome, JanitorPlanText, JanitorRunText};
use crate::json::main::dumps::dumps;
use crate::json::models::{JsonDialect, JsonValue, StdlibJsonOptions};

/// `json.dumps(payload, indent=2)` of the outcome, the plan (none when disabled), run and error.
#[must_use]
pub fn format_janitor_json(
    plan: Option<&JanitorPlanText>,
    outcome: JanitorOutcome,
    run: Option<&JanitorRunText>,
    error: Option<&str>,
) -> String {
    let payload: JsonValue = JsonValue::Object(vec![
        (
            "target".to_owned(),
            plan.and_then(|plan| plan.target_name.as_deref())
                .map_or(JsonValue::Null, |name| JsonValue::String(name.to_owned())),
        ),
        (
            "status".to_owned(),
            JsonValue::String(outcome.value().to_owned()),
        ),
        (
            "plan".to_owned(),
            plan.map_or(JsonValue::Null, plan_payload),
        ),
        (
            "result".to_owned(),
            run.map_or(JsonValue::Null, run_payload),
        ),
        (
            "error".to_owned(),
            error.map_or(JsonValue::Null, |error| JsonValue::String(error.to_owned())),
        ),
    ]);
    dumps(
        &payload,
        &JsonDialect::Stdlib(StdlibJsonOptions::new(Some(2))),
    )
    .unwrap_or_default()
}
