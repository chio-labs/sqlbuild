//! The directories whose listing failed after they opened, for callers that must report it.

use std::sync::PoisonError;

use crate::tree::models::ProjectTree;

/// Relative directories read so far whose `readdir` failed mid-listing, sorted.
pub fn interrupted_listings(tree: &ProjectTree) -> Vec<String> {
    let mut directories: Vec<String> = tree
        .interrupted
        .lock()
        .unwrap_or_else(PoisonError::into_inner)
        .clone();
    directories.sort();
    directories
}
