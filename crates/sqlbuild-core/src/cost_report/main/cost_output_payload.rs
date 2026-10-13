//! The `sqb cost --json` document of one run.

use crate::cost_report::_helpers::payloads::output;
use crate::cost_report::models::CostRun;
use crate::json::models::JsonValue;

/// The run's output document, keys in emission order.
#[must_use]
pub fn cost_output_payload(run: &CostRun) -> JsonValue {
    output(run)
}
