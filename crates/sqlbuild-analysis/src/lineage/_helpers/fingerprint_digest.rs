//! The digest updates of Python's `relation_lineage_fingerprint`, after its prefix.

use std::collections::BTreeSet;
use std::fmt::Write;

use rayon::prelude::{IntoParallelRefIterator, ParallelIterator};
use sha2::{Digest, Sha256};

use crate::lineage::_helpers::authored_files::AuthoredFile;
use crate::lineage::_helpers::environment_markers::environment_names;
use crate::lineage::constants::{
    DYNAMIC_CONTEXT_MARKER, DYNAMIC_CONTEXT_SUFFIXES, MISSING_ENVIRONMENT_VALUE,
};

struct ScannedFile {
    contents: Vec<u8>,
    environment: Vec<String>,
}

/// The hex digest, or `None` where Python returns `None`.
pub(crate) fn fingerprint_digest(files: &[AuthoredFile], prefix: &[u8]) -> Option<String> {
    let scanned: Vec<Option<ScannedFile>> = files.par_iter().map(scanned_file).collect();
    let mut digest = Sha256::new();
    digest.update(prefix);
    let mut environment: BTreeSet<String> = BTreeSet::new();
    for (file, scanned) in files.iter().zip(scanned) {
        let scanned = scanned?;
        environment.extend(scanned.environment);
        let relative_path = file.relative_path();
        digest.update((relative_path.chars().count() as u64).to_be_bytes());
        digest.update(relative_path.as_bytes());
        digest.update((scanned.contents.len() as u64).to_be_bytes());
        digest.update(&scanned.contents);
    }
    for name in &environment {
        digest.update(name.as_bytes());
        digest.update(environment_value(name)?.as_bytes());
    }
    Some(digest.finalize().iter().fold(String::new(), |mut hex, byte| {
        let _ = write!(hex, "{byte:02x}");
        hex
    }))
}

/// `os.environ.get(name, "<missing>")`; `None` where its UTF-8 encoding fails.
fn environment_value(name: &str) -> Option<String> {
    let Some(value) = std::env::var_os(name) else {
        return Some(MISSING_ENVIRONMENT_VALUE.to_owned());
    };
    let Ok(value) = value.into_string() else {
        return None;
    };
    Some(value)
}

/// One file's bytes and environment names; `None` where Python returns `None`.
fn scanned_file(file: &AuthoredFile) -> Option<ScannedFile> {
    let Ok(contents) = std::fs::read(&file.path) else {
        return None;
    };
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
