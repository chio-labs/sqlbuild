//! The note naming type-proof rules skipped because SQL analysis is disabled.

/// The skipped type-proof rules note, or `None` when no rule was skipped.
pub fn format_skipped_rules(codes: &[String]) -> Option<String> {
    if codes.is_empty() {
        return None;
    }
    Some(format!(
        "skipped type-proof rules ({}) because SQL analysis is disabled",
        codes.join(", ")
    ))
}
