//! `MeasurementThresholds.__post_init__`: the warn and error bounds of one audit.

use crate::header_metadata::_helpers::thresholds::check_pair;
use crate::header_metadata::models::ThresholdBound;

/// Whether `warn` and `error` form a valid threshold policy, or the measurement audit error text.
pub fn check_threshold_pair(
    warn: Option<ThresholdBound>,
    error: Option<ThresholdBound>,
) -> Result<(), &'static str> {
    check_pair(warn, error)
}
