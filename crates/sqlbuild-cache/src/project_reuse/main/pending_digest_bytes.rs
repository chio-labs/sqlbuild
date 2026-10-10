use crate::project_reuse::models::ReuseAttempt;

/// Bytes recording this attempt would hash for files whose stamp moved.
pub fn pending_digest_bytes(attempt: &ReuseAttempt) -> u64 {
    crate::project_reuse::_helpers::files::pending_digest_bytes(
        &attempt.snapshot,
        &attempt.digests,
        &attempt.restamped,
    )
}
