//! A standalone measurement audit header's `thresholds` and `minimum_samples`.

use crate::errors::ConfigError;
use crate::header_metadata::_helpers::text::Site;
use crate::header_metadata::_helpers::thresholds::thresholds;
use crate::header_metadata::models::ParsedThresholds;
use crate::types::{AuthoredNode, NodeKind};

/// Parsed thresholds and the authored `minimum_samples` node, or the error at `path`.
pub fn parse_measurement_policy<N: AuthoredNode>(
    policy: (Option<&N>, Option<&N>),
    path: &str,
    label: &str,
) -> Result<(Option<ParsedThresholds>, Option<N>), ConfigError> {
    let site = Site {
        path,
        label,
        column: None,
    };
    let (raw_thresholds, raw_minimum_samples) = policy;
    let parsed: Option<ParsedThresholds> = thresholds(raw_thresholds, site)?;
    let minimum_samples: Option<N> = match raw_minimum_samples.map(AuthoredNode::kind) {
        None | Some(NodeKind::Null) => None,
        Some(NodeKind::Int { negative: false }) => raw_minimum_samples.cloned(),
        Some(_) => return Err(site.error("'minimum_samples' must be a non-negative integer")),
    };
    Ok((parsed, minimum_samples))
}
