//! Discover the effective half-open cursor window from snapshot facts.

use crate::algebra::errors::CursorError;
use crate::algebra::main::cursor_sort_key::cursor_sort_key;
use crate::algebra::main::extreme_position::extreme_position;
use crate::algebra::main::floor_to_grain::floor_to_grain;
use crate::algebra::main::observed_partition::observed_partition;
use crate::algebra::models::{Extreme, Grain, Scalar, ScalarValue};
use crate::algebra::types::ZoneRules;
use crate::planner::models::{CursorKind, CursorSnapshot};

fn extreme(
    values: &[Scalar],
    mode: Extreme,
    zones: &impl ZoneRules,
) -> Result<Scalar, CursorError> {
    let keys = values
        .iter()
        .map(|value| cursor_sort_key(value, zones))
        .collect::<Result<Vec<_>, _>>()?;
    Ok(values[extreme_position(&keys, mode)?].clone())
}

fn discovered_end(value: &Scalar, kind: &CursorKind<'_>) -> Result<Scalar, CursorError> {
    let grain = match kind.cursor_type {
        Some("integer") => None,
        Some("timestamp") => Some(kind.grain.unwrap_or({
            if matches!(value.value, ScalarValue::Timestamp(_)) {
                Grain::Second
            } else {
                Grain::Day
            }
        })),
        _ => return Ok(value.clone()),
    };
    Ok(observed_partition(value, grain)?.end)
}

/// Determine raw start and exclusive end without replay or override policy.
pub fn raw_bounds(
    snapshot: &CursorSnapshot,
    kind: &CursorKind<'_>,
    zones: &impl ZoneRules,
) -> Result<Option<(Scalar, Scalar)>, CursorError> {
    let mut ends: Vec<Scalar> = Vec::new();
    if !snapshot.availability_ends.is_empty() {
        for value in &snapshot.availability_ends {
            ends.push(if kind.cursor_type == Some("timestamp") {
                if let Some(grain) = kind.grain {
                    floor_to_grain(value, Some(grain))
                } else {
                    value.clone()
                }
            } else {
                value.clone()
            });
        }
    } else if !snapshot.end_inputs.is_empty() {
        for (physical, terminal) in &snapshot.end_inputs {
            if let Some(terminal) = terminal {
                ends.push(terminal.clone());
            } else if let Some(physical) = physical {
                ends.push(discovered_end(physical, kind)?);
            }
        }
    } else {
        for value in &snapshot.upstream_maxes {
            ends.push(discovered_end(value, kind)?);
        }
        ends.extend(snapshot.terminal_ends.iter().cloned());
    }
    if ends.is_empty() {
        return Ok(None);
    }
    let end = extreme(
        &ends,
        if snapshot.any_input {
            Extreme::Max
        } else {
            Extreme::Min
        },
        zones,
    )?;
    let start = if let Some(value) = &snapshot.target_max {
        value.clone()
    } else {
        let starts: Vec<Scalar> = snapshot
            .upstream_mins
            .iter()
            .chain(&snapshot.terminal_starts)
            .cloned()
            .collect();
        if starts.is_empty() {
            return Ok(None);
        }
        extreme(&starts, Extreme::Min, zones)?
    };
    Ok(Some((start, end)))
}
