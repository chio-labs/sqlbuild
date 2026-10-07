//! The directory listings a pass has read, for the Python snapshot to share.

use crate::tree::models::{ProjectTree, TreeEntry};
use std::sync::Arc;

/// Every listing read so far as `(relative directory, entries)`, in no particular order.
pub fn read_listings(tree: &ProjectTree) -> Vec<(String, Arc<Vec<TreeEntry>>)> {
    match tree.listings.lock() {
        Ok(listings) => listings
            .iter()
            .map(|(directory, entries)| (directory.clone(), Arc::clone(entries)))
            .collect(),
        Err(_poisoned) => Vec::new(),
    }
}
