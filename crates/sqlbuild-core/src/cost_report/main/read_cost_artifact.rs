//! A decoded `run.json` payload as a cost run.

use crate::cost_report::_helpers::parsing::cost_run;
use crate::cost_report::errors::CostArtifactError;
use crate::cost_report::models::CostRun;
use crate::json::models::JsonValue;

/// The run the payload describes, or why the artifact is unusable.
pub fn read_cost_artifact(payload: &JsonValue) -> Result<CostRun, CostArtifactError> {
    cost_run(payload)
}
