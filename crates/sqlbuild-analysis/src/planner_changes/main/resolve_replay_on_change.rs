//! Parse a model's `replay_on_change` policy.

use crate::planner_changes::constants::{BOUNDED_POLICY_PREFIX, FORWARD_ONLY_POLICY, FULL_POLICY};
use crate::planner_changes::errors::UnknownReplayPolicy;
use crate::planner_changes::models::{Backfill, BackfillAction};

/// The backfill a detected version change replays: forward only, full, or bounded by a duration.
pub fn resolve_replay_on_change(raw: Option<&str>) -> Result<Backfill, UnknownReplayPolicy> {
    let action = |action: BackfillAction, duration: Option<String>| Backfill { action, duration };
    match raw {
        None | Some(FORWARD_ONLY_POLICY) => Ok(action(BackfillAction::ForwardOnly, None)),
        Some(FULL_POLICY) => Ok(action(BackfillAction::Full, None)),
        Some(value) => match value
            .strip_prefix(BOUNDED_POLICY_PREFIX)
            .map(|duration| duration.strip_suffix('\n').unwrap_or(duration))
        {
            Some(duration) if !duration.is_empty() && !duration.contains('\n') => Ok(action(
                BackfillAction::Bounded,
                Some(duration.trim().to_owned()),
            )),
            _ => Err(UnknownReplayPolicy(value.to_owned())),
        },
    }
}
