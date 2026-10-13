//! The status word of a test outcome.

/// `PASS`, `ERROR` for execution errors, else `FAIL`.
#[must_use]
pub fn test_outcome_status(outcome: &str) -> &'static str {
    match outcome {
        "pass" => "PASS",
        "error" => "ERROR",
        _ => "FAIL",
    }
}
