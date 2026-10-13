//! The run a `sqb cost` selector names.

use crate::cost_report::constants::{LATEST_SELECTOR, RUNNING_BUILD_STATUS};
use crate::cost_report::models::CostRun;

/// `latest` picks the newest finished run; otherwise the only run whose ID starts with the selector.
#[must_use]
pub fn select_cost_run(runs: Vec<CostRun>, selector: &str) -> Option<CostRun> {
    if selector == LATEST_SELECTOR {
        return runs
            .into_iter()
            .find(|run| run.build_status != RUNNING_BUILD_STATUS);
    }
    let mut matches = runs
        .into_iter()
        .filter(|run| run.run_id.starts_with(selector));
    let first: CostRun = matches.next()?;
    matches.next().is_none().then_some(first)
}
