//! `implementation_fingerprint`: SHA-256 of a rule file and its imported helper closure.

use std::path::Path;

use sha2::{Digest, Sha256};

/// The digest of each file's root-relative label and bytes, rule source first.
pub fn implementation_fingerprint(
    source_path: &Path,
    closure: &[impl AsRef<Path>],
    root: &Path,
) -> std::io::Result<String> {
    let mut digest = Sha256::new();
    for path in std::iter::once(source_path).chain(closure.iter().map(AsRef::as_ref)) {
        let label: &Path = path.strip_prefix(root).unwrap_or(path);
        digest.update(label.to_string_lossy().as_bytes());
        digest.update(b"\0");
        digest.update(std::fs::read(path)?);
    }
    Ok(format!("{:x}", digest.finalize()))
}
