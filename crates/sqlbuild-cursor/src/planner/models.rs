//! Inputs to planner cursor-window algebra.

use crate::algebra::models::{DurationSpan, Grain, Scalar};

/// Discovered values used to determine a half-open cursor window.
#[derive(Debug)]
pub struct CursorSnapshot {
    pub target_max: Option<Scalar>,
    pub upstream_mins: Vec<Scalar>,
    pub upstream_maxes: Vec<Scalar>,
    pub terminal_starts: Vec<Scalar>,
    pub terminal_ends: Vec<Scalar>,
    pub end_inputs: Vec<(Option<Scalar>, Option<Scalar>)>,
    pub availability_ends: Vec<Scalar>,
    pub any_input: bool,
}

/// Cursor representation and discovered partition grain.
#[derive(Debug)]
pub struct CursorKind<'a> {
    pub cursor_type: Option<&'a str>,
    pub grain: Option<Grain>,
}

/// Parsed replay durations and configured lower bound.
#[derive(Debug)]
pub struct ReplayPolicy {
    pub floor: Option<Scalar>,
    pub lookback: Option<DurationSpan>,
    pub backfill: Option<DurationSpan>,
    pub has_backfill: bool,
    pub has_start_override: bool,
}

/// The change a configured exclusive `cursor_end` makes to a concrete window.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CursorEndClamp {
    /// The window already ends at or before `cursor_end`.
    Unchanged,
    /// The window starts at or after `cursor_end`, so it collapses to `[cursor_end, cursor_end)`.
    Empty,
    /// The window ends after `cursor_end`, so its end becomes `cursor_end`.
    Capped,
}
