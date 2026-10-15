//! `MeasurementThresholdBound.__post_init__`: one directional bound and its limits.

use crate::header_metadata::constants::{ABOVE_OPERATOR, BELOW_OPERATOR};
use crate::header_metadata::models::{ThresholdBound, ThresholdInput};

/// The bound `operator` declares over `(limit, lower, upper)`, or the measurement audit error text.
pub fn check_threshold_bound(
    operator: &str,
    (limit, lower, upper): (ThresholdInput, ThresholdInput, ThresholdInput),
) -> Result<ThresholdBound, String> {
    if operator == BELOW_OPERATOR || operator == ABOVE_OPERATOR {
        let limit: f64 = match (limit, lower, upper) {
            (ThresholdInput::Number(limit), ThresholdInput::Absent, ThresholdInput::Absent) => {
                limit
            }
            (ThresholdInput::Boolean, ThresholdInput::Absent, ThresholdInput::Absent) => {
                return Err("measurement threshold limit must not be boolean".to_owned());
            }
            _ => return Err(format!("{operator} threshold requires limit only")),
        };
        if !limit.is_finite() {
            return Err("measurement threshold limit must be finite".to_owned());
        }
        return Ok(if operator == BELOW_OPERATOR {
            ThresholdBound::Below(limit)
        } else {
            ThresholdBound::Above(limit)
        });
    }
    if limit != ThresholdInput::Absent
        || lower == ThresholdInput::Absent
        || upper == ThresholdInput::Absent
    {
        return Err("outside threshold requires lower and upper only".to_owned());
    }
    let ThresholdInput::Number(lower) = lower else {
        return Err("measurement threshold lower must not be boolean".to_owned());
    };
    let ThresholdInput::Number(upper) = upper else {
        return Err("measurement threshold upper must not be boolean".to_owned());
    };
    if !lower.is_finite() {
        return Err("measurement threshold lower must be finite".to_owned());
    }
    if !upper.is_finite() {
        return Err("measurement threshold upper must be finite".to_owned());
    }
    if lower > upper {
        return Err("outside threshold lower must be less than or equal to upper".to_owned());
    }
    Ok(ThresholdBound::Outside(lower, upper))
}
