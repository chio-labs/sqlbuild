//! Read a `--downstream` or `[review] downstream` value.

use crate::review_command::constants::{ALL_POLICY, CRITICAL_POLICY, NONE_POLICY};
use crate::review_command::models::DownstreamPolicy;

/// The policy `value` names, or `None` for an unknown value.
#[must_use]
pub fn parse_downstream_policy(value: &str) -> Option<DownstreamPolicy> {
    match value {
        CRITICAL_POLICY => Some(DownstreamPolicy::Critical),
        ALL_POLICY => Some(DownstreamPolicy::All),
        NONE_POLICY => Some(DownstreamPolicy::None),
        _ => None,
    }
}
