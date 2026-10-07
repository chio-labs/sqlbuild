//! Fingerprint the content of a project's files, leaving out the files a cache key covers itself.

use rayon::prelude::{IntoParallelRefIterator, ParallelIterator};
use sha2::{Digest, Sha256};
use std::collections::HashSet;
use std::path::Path;

use crate::digest::_helpers::walk::{CoveredFile, covered_files};
use crate::digest::constants::{CONTENT_TAG, PRESENCE_TAG};
use crate::digest::errors::FingerprintError;
use crate::digest::main::content_digest::content_digest;
use crate::digest::types::ContentDigest;

/// Digest every covered file's project-relative path and bytes; fails if any file is unreadable.
pub fn fingerprint_project_files(
    root: &Path,
    excluded_files: &HashSet<String>,
) -> Result<ContentDigest, FingerprintError> {
    let files: Vec<CoveredFile> = covered_files(root, excluded_files)?;
    let digests: Vec<ContentDigest> = files
        .par_iter()
        .map(file_digest)
        .collect::<Result<Vec<ContentDigest>, FingerprintError>>()?;
    let mut hasher: Sha256 = Sha256::new();
    for (file, digest) in files.iter().zip(digests) {
        hasher.update(content_digest(&[file.relative_path.as_bytes(), &digest]));
    }
    Ok(hasher.finalize().into())
}

fn file_digest(file: &CoveredFile) -> Result<ContentDigest, FingerprintError> {
    if file.presence_only {
        return Ok(content_digest(&[PRESENCE_TAG]));
    }
    let bytes: Vec<u8> = std::fs::read(&file.path)
        .map_err(|error| FingerprintError::Read(file.path.clone(), error))?;
    Ok(content_digest(&[CONTENT_TAG, &bytes]))
}
