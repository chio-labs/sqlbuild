//! Python's `relation_lineage_fingerprint` over the authored files, after its prefix.

use std::path::Path;

use crate::lineage::_helpers::authored_files::authored_files;
use crate::lineage::_helpers::fingerprint_digest::fingerprint_outcome;
use crate::lineage::models::{InterruptedListingPolicy, RelationFingerprint};

/// Hash Python's encoded `prefix`, the authored files and the environment values they read.
pub fn relation_fingerprint(
    project_dir: &Path,
    prefix: &[u8],
    policy: InterruptedListingPolicy,
) -> RelationFingerprint {
    fingerprint_outcome(authored_files(project_dir), prefix, policy)
}
