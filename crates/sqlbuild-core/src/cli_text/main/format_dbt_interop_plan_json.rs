//! `sqb dbt plan --json`.

use crate::cli_text::_helpers::dbt_plan_json::dbt_plan_payload;
use crate::cli_text::models::DbtInteropPlanText;
use crate::json::main::dumps::dumps;
use crate::json::models::{JsonDialect, JsonValue, StdlibJsonOptions};

/// `json.dumps(payload, indent=2)` of the plan's dbt and SQLBuild work.
#[must_use]
pub fn format_dbt_interop_plan_json(plan: &DbtInteropPlanText) -> String {
    let payload: JsonValue = dbt_plan_payload(plan);
    dumps(
        &payload,
        &JsonDialect::Stdlib(StdlibJsonOptions::new(Some(2))),
    )
    .unwrap_or_default()
}
