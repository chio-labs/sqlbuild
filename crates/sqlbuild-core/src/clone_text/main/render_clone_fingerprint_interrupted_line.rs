//! Bounded context for interrupted clone fingerprint propagation.

use crate::cli_text::models::CliStyle;
use crate::clone_text::constants::{
    FINGERPRINT_LABEL, FINGERPRINT_LABEL_WIDTH, PENDING_IDENTITY_LIMIT,
};
use crate::clone_text::models::FingerprintProgress;

/// The confirmed count and up to ten pending identities; none once everything was confirmed.
#[must_use]
pub fn render_clone_fingerprint_interrupted_line(
    progress: &FingerprintProgress,
    style: CliStyle,
) -> Option<String> {
    if progress.total <= progress.completed {
        return None;
    }
    let shown: usize = progress
        .pending_identities
        .len()
        .min(PENDING_IDENTITY_LIMIT);
    let remaining: usize = progress.pending_identities.len() - shown;
    let mut pending: String = progress.pending_identities[..shown].join(", ");
    if remaining > 0 {
        pending = format!("{pending} (+{remaining} more)");
    }
    Some(format!(
        "  {FINGERPRINT_LABEL:<FINGERPRINT_LABEL_WIDTH$}[{}/{}] {} not confirmed: {pending}",
        progress.completed,
        progress.total,
        style.status("FAIL")
    ))
}
