//! The per-project lock file name that serializes generated skill installation.

use sha2::{Digest, Sha256};

/// `<sha256 of the case-normalized project path>.lock`.
pub fn skill_lock_name(canonical_project: &str) -> String {
    format!("{:x}.lock", Sha256::digest(canonical_project.as_bytes()))
}
