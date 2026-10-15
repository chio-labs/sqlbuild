//! The plan direction and phase of one rendered retention change.

use crate::planner_warehouse::constants::{
    CHANGE_PHASE_FINALIZE, CHANGE_PHASE_PREPARE, RETENTION_DECREASE, RETENTION_INCREASE,
    RETENTION_PHASE_POST, RETENTION_PHASE_PRE,
};

/// `(direction, phase)` for a change phase, falling back to the state direction.
pub fn retention_change<'a>(change_phase: &str, fallback: &'a str) -> (&'a str, &'static str) {
    if change_phase == CHANGE_PHASE_PREPARE {
        (RETENTION_INCREASE, RETENTION_PHASE_PRE)
    } else if change_phase == CHANGE_PHASE_FINALIZE {
        (RETENTION_DECREASE, RETENTION_PHASE_POST)
    } else if fallback == RETENTION_INCREASE {
        (fallback, RETENTION_PHASE_PRE)
    } else {
        (fallback, RETENTION_PHASE_POST)
    }
}
