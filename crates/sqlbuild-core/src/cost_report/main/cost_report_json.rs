//! `sqb cost --json` text of one run.

use crate::cost_report::_helpers::payloads::output;
use crate::cost_report::models::CostRun;
use crate::json::main::dumps::dumps;
use crate::json::models::{JsonDialect, StdlibJsonOptions};

/// `json.dumps(cost_output_payload(record), indent=2, sort_keys=True)`.
#[must_use]
pub fn cost_report_json(run: &CostRun) -> String {
    let options: StdlibJsonOptions = StdlibJsonOptions {
        sort_keys: true,
        ..StdlibJsonOptions::new(Some(2))
    };
    dumps(&output(run), &JsonDialect::Stdlib(options)).unwrap_or_default()
}
