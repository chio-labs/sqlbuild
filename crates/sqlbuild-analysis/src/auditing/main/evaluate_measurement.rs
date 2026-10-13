//! `evaluate_measurement`: the outcome of one measured value under its sample and threshold policy.

use crate::auditing::models::{MeasurementOutcome, ThresholdBound, Thresholds};

fn violates(measured: f64, bound: ThresholdBound) -> bool {
    match bound {
        ThresholdBound::Below(limit) => measured < limit,
        ThresholdBound::Above(limit) => measured > limit,
        ThresholdBound::Outside(lower, upper) => measured < lower || measured > upper,
    }
}

/// The outcome of a finite measurement; `(sample_count, minimum_samples)` gate sufficiency.
pub fn evaluate_measurement(
    measured: f64,
    (sample_count, minimum_samples): (Option<i128>, Option<i128>),
    thresholds: Thresholds,
) -> Result<MeasurementOutcome, &'static str> {
    if !measured.is_finite() {
        return Err("measured_value must be finite");
    }
    if let Some(minimum) = minimum_samples
        && sample_count.is_none_or(|count| count < minimum)
    {
        return Ok(MeasurementOutcome::Insufficient);
    }
    if thresholds
        .error
        .is_some_and(|bound| violates(measured, bound))
    {
        return Ok(MeasurementOutcome::Error);
    }
    if thresholds
        .warn
        .is_some_and(|bound| violates(measured, bound))
    {
        return Ok(MeasurementOutcome::Warn);
    }
    Ok(MeasurementOutcome::Pass)
}
