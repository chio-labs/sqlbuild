//! Clamping a concrete cursor window to an exclusive configured `cursor_end`.

use std::cmp::Ordering;

use crate::algebra::errors::CursorError;
use crate::algebra::main::compare::compare;
use crate::algebra::models::Scalar;
use crate::algebra::types::ZoneRules;
use crate::planner::models::CursorEndClamp;

/// How a `[start, end)` window changes so it never reaches past `cursor_end`.
pub fn cursor_end_clamp(
    window: (&Scalar, &Scalar),
    cursor_end: &Scalar,
    rules: &impl ZoneRules,
) -> Result<CursorEndClamp, CursorError> {
    let (start, end) = window;
    if compare(start, cursor_end, rules)? != Ordering::Less {
        return Ok(CursorEndClamp::Empty);
    }
    if compare(end, cursor_end, rules)? == Ordering::Greater {
        return Ok(CursorEndClamp::Capped);
    }
    Ok(CursorEndClamp::Unchanged)
}
