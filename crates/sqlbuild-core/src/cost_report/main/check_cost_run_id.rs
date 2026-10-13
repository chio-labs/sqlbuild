//! The path-safety rule of cost run IDs.

use crate::cost_report::_helpers::parsing::check_run_id;
use crate::cost_report::errors::CostArtifactError;

/// A run ID must be exactly one path component other than `.` and `..`.
pub fn check_cost_run_id(run_id: &str) -> Result<(), CostArtifactError> {
    check_run_id(run_id)
}
