//! `sqb cost history --json` text.

use crate::cost_report::_helpers::payloads::history;
use crate::cost_report::models::CostRun;
use crate::json::main::dumps::dumps;
use crate::json::models::{JsonDialect, StdlibJsonOptions};

/// The history document of the shown runs; `matching_count` defaults to their number.
#[must_use]
pub fn cost_history_json(runs: &[CostRun], matching_count: Option<usize>) -> String {
    let options: StdlibJsonOptions = StdlibJsonOptions {
        sort_keys: true,
        ..StdlibJsonOptions::new(Some(2))
    };
    dumps(
        &history(runs, matching_count),
        &JsonDialect::Stdlib(options),
    )
    .unwrap_or_default()
}
