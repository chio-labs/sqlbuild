//! Python's `relation_lineage_fingerprint` over the authored files, after its prefix.

use std::path::Path;

use crate::lineage::_helpers::authored_files::authored_files;
use crate::lineage::_helpers::fingerprint_digest::fingerprint_digest;
use crate::lineage::models::RelationFingerprint;

/// Hash Python's encoded `prefix`, the authored files and the environment values they read.
pub fn relation_fingerprint(project_dir: &Path, prefix: &[u8]) -> RelationFingerprint {
    if cfg!(windows) {
        return RelationFingerprint::Deferred;
    }
    let Some(files) = authored_files(project_dir) else {
        return RelationFingerprint::Deferred;
    };
    fingerprint_digest(&files, prefix).map_or(
        RelationFingerprint::Uncacheable,
        RelationFingerprint::Digest,
    )
}
