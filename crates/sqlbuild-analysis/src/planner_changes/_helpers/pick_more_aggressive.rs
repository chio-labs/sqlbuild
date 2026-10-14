//! Choose between two backfills.

use crate::planner_changes::models::{Backfill, BackfillAction};

/// The more aggressive backfill (full over bounded over forward only); a tie keeps `first`.
pub(crate) fn pick_more_aggressive(first: Backfill, second: Backfill) -> Backfill {
    if priority(first.action) >= priority(second.action) {
        first
    } else {
        second
    }
}

fn priority(action: BackfillAction) -> u8 {
    match action {
        BackfillAction::ForwardOnly => 0,
        BackfillAction::Bounded => 1,
        BackfillAction::Full => 2,
    }
}
