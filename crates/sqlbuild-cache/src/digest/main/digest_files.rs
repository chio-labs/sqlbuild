//! BLAKE3 content digests of individual files, read and hashed in parallel.

use rayon::prelude::{IntoParallelRefIterator, ParallelIterator};
use std::path::PathBuf;

use crate::digest::types::ContentDigest;

/// The digest of each file in `paths`; BLAKE3 keeps large compiled modules cheap to hash.
pub fn digest_files(paths: &[PathBuf]) -> Vec<std::io::Result<ContentDigest>> {
    paths.par_iter().map(file_digest).collect()
}

fn file_digest(path: &PathBuf) -> std::io::Result<ContentDigest> {
    let bytes: Vec<u8> = std::fs::read(path)?;
    let mut hasher = blake3::Hasher::new();
    let _ = hasher.update_rayon(&bytes);
    Ok(*hasher.finalize().as_bytes())
}
