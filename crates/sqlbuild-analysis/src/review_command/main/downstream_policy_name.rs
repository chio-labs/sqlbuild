//! The name a `--downstream` policy is written with.

use crate::review_command::_helpers::wording::policy_name;
use crate::review_command::models::DownstreamPolicy;

/// `critical`, `all` or `none`.
#[must_use]
pub fn downstream_policy_name(policy: DownstreamPolicy) -> &'static str {
    policy_name(policy)
}
