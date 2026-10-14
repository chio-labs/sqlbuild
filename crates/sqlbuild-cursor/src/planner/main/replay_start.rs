//! Replay windows and configured cursor floors.

use std::cmp::Ordering;

use crate::algebra::errors::CursorError;
use crate::algebra::main::compare::compare;
use crate::algebra::main::shift_by_duration::shift_by_duration;
use crate::algebra::models::{
    DurationSpan, LocalDateTime, Moment, Scalar, ScalarValue, Timestamp, ZoneOffset,
};
use crate::algebra::types::ZoneRules;
use crate::planner::models::{CursorKind, ReplayPolicy};

fn timestamp(value: &Scalar) -> Option<Scalar> {
    match value.value {
        ScalarValue::Timestamp(_) => Some(value.clone()),
        ScalarValue::Date(date) => Some(Scalar {
            value: ScalarValue::Timestamp(Timestamp {
                local: LocalDateTime {
                    date,
                    hour: 0,
                    minute: 0,
                    second: 0,
                    microsecond: 0,
                },
                fold: false,
                offset: ZoneOffset::Naive,
                template: None,
                source_text: None,
            }),
            handle: None,
        }),
        ScalarValue::Integer(_) => None,
    }
}

fn subtract(value: &Scalar, span: &DurationSpan) -> Result<Scalar, CursorError> {
    if let ScalarValue::Integer(integer) = value.value {
        let seconds = i128::from(span.days) * 86_400
            + i128::from(span.hours) * 3_600
            + i128::from(span.minutes) * 60
            + i128::from(span.seconds);
        return Ok(Scalar {
            value: ScalarValue::Integer(integer - seconds),
            handle: None,
        });
    }
    let Some(mut result) = timestamp(value) else {
        return Ok(value.clone());
    };
    if let ScalarValue::Timestamp(ref mut value) = result.value {
        let shifted = shift_by_duration(
            Moment::Timestamp {
                local: value.local,
                fold: value.fold,
            },
            span,
            -1,
        )?;
        if let Moment::Timestamp { local, fold } = shifted {
            value.local = local;
            value.fold = fold;
            value.source_text = None;
        }
    }
    result.handle = None;
    Ok(result)
}

/// Apply replay and lower-bound policy to a typed cursor start.
pub fn replay_start(
    bounds: (&Scalar, &Scalar),
    policy: &ReplayPolicy,
    kind: &CursorKind<'_>,
    zones: &impl ZoneRules,
) -> Result<Scalar, CursorError> {
    let (start, end) = bounds;
    let mut effective = start.clone();
    if !policy.has_start_override {
        if policy.has_backfill {
            if let Some(span) = &policy.backfill {
                effective = subtract(end, span)?;
            }
        } else if let Some(span) = &policy.lookback {
            effective = subtract(&effective, span)?;
        }
    }
    let Some(floor) = &policy.floor else {
        return Ok(effective);
    };
    let pair = match kind.cursor_type {
        Some("timestamp") => timestamp(&effective).zip(timestamp(floor)),
        Some("integer") => Some((effective.clone(), floor.clone())),
        _ => None,
    };
    if let Some((current, floor)) = pair {
        return Ok(if compare(&floor, &current, zones)? == Ordering::Greater {
            floor
        } else {
            current
        });
    }
    Ok(effective)
}
