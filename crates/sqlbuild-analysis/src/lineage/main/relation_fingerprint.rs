//! Python's `relation_lineage_fingerprint` over the authored files, after its prefix.

use std::collections::BTreeSet;
use std::fmt::Write;
use std::path::Path;

use rayon::prelude::{IntoParallelRefIterator, ParallelIterator};
use sha2::{Digest, Sha256};

use crate::lineage::_helpers::authored_files::{AuthoredFile, authored_files};
use crate::lineage::_helpers::environment_markers::environment_names;
use crate::lineage::constants::{
    DYNAMIC_CONTEXT_MARKER, DYNAMIC_CONTEXT_SUFFIXES, MISSING_ENVIRONMENT_VALUE,
};
use crate::lineage::models::RelationFingerprint;

/// Hash `prefix` (algorithm, version and variables, which Python encodes), every authored file
/// and the environment values they read, exactly as Python does.
pub fn relation_fingerprint(project_dir: &Path, prefix: &[u8]) -> RelationFingerprint {
    if cfg!(windows) {
        return RelationFingerprint::Deferred;
    }
    let Some(files) = authored_files(project_dir) else {
        return RelationFingerprint::Deferred;
    };
    let scanned: Vec<Option<ScannedFile>> = files.par_iter().map(scanned_file).collect();
    let mut digest = Sha256::new();
    digest.update(prefix);
    let mut environment: BTreeSet<String> = BTreeSet::new();
    for (file, scanned) in files.iter().zip(scanned) {
        let Some(scanned) = scanned else {
            return RelationFingerprint::Uncacheable;
        };
        environment.extend(scanned.environment);
        let relative_path = file.relative_path();
        digest.update((relative_path.chars().count() as u64).to_be_bytes());
        digest.update(relative_path.as_bytes());
        digest.update((scanned.contents.len() as u64).to_be_bytes());
        digest.update(&scanned.contents);
    }
    for name in &environment {
        digest.update(name.as_bytes());
        match std::env::var_os(name) {
            None => digest.update(MISSING_ENVIRONMENT_VALUE.as_bytes()),
            Some(value) => match value.into_string() {
                Ok(value) => digest.update(value.as_bytes()),
                Err(_) => return RelationFingerprint::Uncacheable,
            },
        }
    }
    let mut hex = String::with_capacity(64);
    for byte in digest.finalize() {
        let _ = write!(hex, "{byte:02x}");
    }
    RelationFingerprint::Digest(hex)
}

struct ScannedFile {
    contents: Vec<u8>,
    environment: Vec<String>,
}

/// One file's bytes and environment names; `None` where Python returns `None`.
fn scanned_file(file: &AuthoredFile) -> Option<ScannedFile> {
    let contents: Vec<u8> = std::fs::read(&file.path).ok()?;
    if contains(&contents, DYNAMIC_CONTEXT_MARKER)
        && DYNAMIC_CONTEXT_SUFFIXES.contains(&file.lower_suffix().as_str())
    {
        return None;
    }
    let environment: Vec<String> = environment_names(&contents)?
        .into_iter()
        .map(str::to_owned)
        .collect();
    Some(ScannedFile {
        contents,
        environment,
    })
}

fn contains(haystack: &[u8], needle: &[u8]) -> bool {
    haystack.windows(needle.len()).any(|window| window == needle)
}
