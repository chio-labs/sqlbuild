//! `hook_problem`: the catalogue rules of an operation's hook fields.

use crate::lifecycle_events::constants::{HOOK_PHASES, HOOK_TYPES};
use crate::lifecycle_events::models::HookFacts;

/// The first rule supplied hook fields break.
#[must_use]
pub fn hook_problem(hook: HookFacts<'_>) -> Option<&'static str> {
    if !hook.phase.is_some_and(|phase| HOOK_PHASES.contains(&phase)) {
        return Some("hook_phase must be a catalogued value");
    }
    if !hook
        .hook_type
        .is_some_and(|hook_type| HOOK_TYPES.contains(&hook_type))
    {
        return Some("hook_type must be a catalogued value");
    }
    (!hook.valid_index).then_some("hook_index must be a nonnegative integer")
}
