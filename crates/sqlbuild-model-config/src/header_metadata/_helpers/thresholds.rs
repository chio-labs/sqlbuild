//! Audit `thresholds`, as `parse_measurement_thresholds` and the threshold models check them.

use crate::errors::ConfigError;
use crate::header_metadata::_helpers::text::{Site, entry};
use crate::header_metadata::constants::{
    THRESHOLD_ERROR_KEY, THRESHOLD_OPERATORS, THRESHOLD_WARN_KEY,
};
use crate::header_metadata::models::{ParsedThresholds, ThresholdBound};
use crate::types::{AuthoredNode, NodeKind};

/// Parse an audit's authored `thresholds`; Python's `None` declares none.
pub(crate) fn thresholds<N: AuthoredNode>(
    node: Option<&N>,
    site: Site<'_>,
) -> Result<Option<ParsedThresholds>, ConfigError> {
    let Some(node) = node.filter(|value| value.kind() != NodeKind::Null) else {
        return Ok(None);
    };
    if node.kind() != NodeKind::Map {
        return Err(site.error("'thresholds' must be a mapping"));
    }
    let entries = node.entries();
    let unknown: Vec<String> = entries
        .iter()
        .filter(|(key, _)| !key.is_text(THRESHOLD_WARN_KEY) && !key.is_text(THRESHOLD_ERROR_KEY))
        .map(|(key, _)| key.python_str())
        .collect();
    if !unknown.is_empty() {
        return Err(site.error(&format!(
            "'thresholds' has unsupported keys: {}",
            unknown.join(", ")
        )));
    }
    let invalid = |problem: &str| site.error(&format!("invalid thresholds: {problem}"));
    let warn = bound(entry(&entries, THRESHOLD_WARN_KEY)).map_err(invalid)?;
    let error = bound(entry(&entries, THRESHOLD_ERROR_KEY)).map_err(invalid)?;
    check_pair(warn, error).map_err(invalid)?;
    Ok(Some(ParsedThresholds { warn, error }))
}

/// Parse one `warn` or `error` bound, returning `MeasurementAuditError`'s text on failure.
fn bound<N: AuthoredNode>(node: Option<&N>) -> Result<Option<ThresholdBound>, &'static str> {
    let Some(node) = node.filter(|value| value.kind() != NodeKind::Null) else {
        return Ok(None);
    };
    let entries = node.entries();
    let [(operator, limit)] = entries.as_slice() else {
        return Err("each threshold must be exactly one of below, above, or outside");
    };
    if node.kind() != NodeKind::Map {
        return Err("each threshold must be exactly one of below, above, or outside");
    }
    let Some(operator) = THRESHOLD_OPERATORS
        .iter()
        .find(|name| operator.is_text(name))
    else {
        return Err("threshold operator must be one of below, above, or outside");
    };
    match *operator {
        "outside" => outside_bound(limit),
        "below" => Ok(Some(ThresholdBound::Below(finite_limit(
            limit,
            "below threshold requires one numeric value",
        )?))),
        _ => Ok(Some(ThresholdBound::Above(finite_limit(
            limit,
            "above threshold requires one numeric value",
        )?))),
    }
}

fn outside_bound<N: AuthoredNode>(limit: &N) -> Result<Option<ThresholdBound>, &'static str> {
    let items = limit.items();
    let numbers: Option<Vec<f64>> = items.iter().map(AuthoredNode::number).collect();
    let (NodeKind::Tuple, Some([lower, upper])) = (limit.kind(), numbers.as_deref()) else {
        return Err("outside threshold requires two numeric values");
    };
    if !lower.is_finite() {
        return Err("measurement threshold lower must be finite");
    }
    if !upper.is_finite() {
        return Err("measurement threshold upper must be finite");
    }
    if lower > upper {
        return Err("outside threshold lower must be less than or equal to upper");
    }
    Ok(Some(ThresholdBound::Outside(*lower, *upper)))
}

fn finite_limit<N: AuthoredNode>(
    limit: &N,
    not_numeric: &'static str,
) -> Result<f64, &'static str> {
    let number = limit.number().ok_or(not_numeric)?;
    if number.is_finite() {
        Ok(number)
    } else {
        Err("measurement threshold limit must be finite")
    }
}

/// Check `MeasurementThresholds.__post_init__` for the parsed bounds.
fn check_pair(
    warn: Option<ThresholdBound>,
    error: Option<ThresholdBound>,
) -> Result<(), &'static str> {
    match (warn, error) {
        (None, None) => Err("at least one measurement threshold is required"),
        (Some(ThresholdBound::Below(warn)), Some(ThresholdBound::Below(error))) => {
            if error >= warn {
                Err("below error limit must be less than warn limit")
            } else {
                Ok(())
            }
        }
        (Some(ThresholdBound::Above(warn)), Some(ThresholdBound::Above(error))) => {
            if error <= warn {
                Err("above error limit must be greater than warn limit")
            } else {
                Ok(())
            }
        }
        (
            Some(ThresholdBound::Outside(warn_lower, warn_upper)),
            Some(ThresholdBound::Outside(error_lower, error_upper)),
        ) => {
            if error_lower >= warn_lower || error_upper <= warn_upper {
                Err("outside error range must strictly contain warn range")
            } else {
                Ok(())
            }
        }
        (Some(_), Some(_)) => Err("mixed measurement threshold operators are unsupported in v1"),
        _ => Ok(()),
    }
}
