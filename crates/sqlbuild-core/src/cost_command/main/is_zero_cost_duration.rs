//! A `--since` of zero days, hours or minutes.

/// Whether the value is one or more zeros followed by `d`, `h` or `m`.
#[must_use]
pub fn is_zero_cost_duration(value: &str) -> bool {
    let Some(digits) = value.strip_suffix(['d', 'h', 'm']) else {
        return false;
    };
    !digits.is_empty() && digits.bytes().all(|byte| byte == b'0')
}
