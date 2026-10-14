//! Invocation-anchored automatic cursor horizon shared by both safety policies.

use crate::algebra::errors::CursorError;
use crate::algebra::main::floor_to_grain::floor_to_grain;
use crate::algebra::main::shift_by_duration::shift_by_duration;
use crate::algebra::models::{DurationSpan, Grain, Moment, Scalar, ScalarValue};

/// Shift a UTC invocation clock, retaining the discovered cursor's date representation.
pub fn safety_horizon(
    clock: &Scalar,
    duration: &DurationSpan,
    grain: Grain,
    date_only: bool,
) -> Result<Scalar, CursorError> {
    let ScalarValue::Timestamp(timestamp) = &clock.value else {
        return Err(CursorError::Type(
            "invocation clock must be a timestamp".into(),
        ));
    };
    let Moment::Timestamp { local, fold } = shift_by_duration(
        Moment::Timestamp {
            local: timestamp.local,
            fold: timestamp.fold,
        },
        duration,
        1,
    )?
    else {
        return Err(CursorError::Type(
            "invocation clock must be a timestamp".into(),
        ));
    };
    let value = if date_only {
        ScalarValue::Date(local.date)
    } else {
        let mut maximum = timestamp.clone();
        maximum.local = local;
        maximum.fold = fold;
        maximum.source_text = None;
        ScalarValue::Timestamp(maximum)
    };
    Ok(floor_to_grain(
        &Scalar {
            value,
            handle: None,
        },
        Some(grain),
    ))
}
