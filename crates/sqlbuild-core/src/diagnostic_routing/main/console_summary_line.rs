//! `console_summary_line`: the one line a summarized console record shows.

/// The first line of `message`, without trailing whitespace.
#[must_use]
pub fn console_summary_line(message: &str) -> &str {
    message.lines().next().unwrap_or_default().trim_end()
}
