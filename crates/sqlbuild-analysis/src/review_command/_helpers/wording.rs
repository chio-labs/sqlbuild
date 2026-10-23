//! Words the review renders for policies, statuses and counts.

use crate::review_command::constants::{
    ALL_POLICY, CRITICAL_POLICY, NONE_POLICY, SECONDS_PER_MINUTE,
};
use crate::review_command::models::DownstreamPolicy;

pub(crate) fn policy_name(policy: DownstreamPolicy) -> &'static str {
    match policy {
        DownstreamPolicy::Critical => CRITICAL_POLICY,
        DownstreamPolicy::All => ALL_POLICY,
        DownstreamPolicy::None => NONE_POLICY,
    }
}

/// `1 model`, `2 models`.
pub(crate) fn counted(count: usize, singular: &str, plural: &str) -> String {
    if count == 1 {
        format!("1 {singular}")
    } else {
        format!("{count} {plural}")
    }
}

/// `3.25s` or `2m 05s`.
pub(crate) fn duration_text(seconds: f64) -> String {
    let whole: u64 = seconds.round() as u64;
    if whole < SECONDS_PER_MINUTE {
        return format!("{seconds:.2}s");
    }
    format!(
        "{}m {:02}s",
        whole / SECONDS_PER_MINUTE,
        whole % SECONDS_PER_MINUTE
    )
}

/// `a`, `a and b`, `a, b and c`.
pub(crate) fn joined(words: &[String]) -> String {
    match words {
        [] => String::new(),
        [only] => only.clone(),
        [init @ .., last] => format!("{} and {last}", init.join(", ")),
    }
}
