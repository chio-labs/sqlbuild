//! The persisted `run.json` text of a cost run.

use crate::cost_report::_helpers::payloads::artifact;
use crate::cost_report::models::CostRun;
use crate::json::main::dumps::dumps;
use crate::json::models::{JsonDialect, StdlibJsonOptions};

/// `json.dumps(asdict(record), indent=2, sort_keys=True) + "\n"`.
#[must_use]
pub fn cost_artifact_text(run: &CostRun) -> String {
    let options: StdlibJsonOptions = StdlibJsonOptions {
        sort_keys: true,
        ..StdlibJsonOptions::new(Some(2))
    };
    dumps(&artifact(run), &JsonDialect::Stdlib(options)).unwrap_or_default() + "\n"
}
