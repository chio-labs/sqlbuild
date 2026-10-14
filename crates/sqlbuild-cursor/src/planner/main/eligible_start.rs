//! Eligible automatic-start fallback selection.

use crate::algebra::errors::CursorError;
use crate::algebra::main::compare::compare;
use crate::algebra::models::Scalar;
use crate::algebra::types::ZoneRules;
use std::cmp::Ordering;

/// Prefer a discovered eligible target, then an eligible upstream minimum.
pub fn eligible_start(
    target: Option<&Scalar>,
    upstream: &[Scalar],
    horizon: &Scalar,
    zones: &impl ZoneRules,
) -> Result<Option<Scalar>, CursorError> {
    if let Some(target) = target {
        return Ok(Some(target.clone()));
    }
    let mut minimum: Option<&Scalar> = None;
    for value in upstream {
        if minimum.is_none() || compare(value, minimum.unwrap_or(value), zones)? == Ordering::Less {
            minimum = Some(value);
        }
    }
    if let Some(minimum) = minimum
        && compare(minimum, horizon, zones)? != Ordering::Greater
    {
        return Ok(Some(minimum.clone()));
    }
    Ok(None)
}
