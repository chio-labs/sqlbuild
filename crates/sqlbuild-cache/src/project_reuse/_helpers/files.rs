//! Project file comparison and content digests, as Python's compile reuse computes them.

use std::collections::{HashMap, HashSet};
use std::path::{Path, PathBuf};

use crate::digest::main::digest_files::digest_files;
use crate::digest::main::hex_digest::hex_digest;
use crate::project_reuse::constants::NATIVE_DIGEST_PREFIX;
use crate::project_reuse::models::{ReuseAttempt, StoredProjectFile};
use crate::project_snapshot::models::PathStamp;

const FILE: &str = "f";
const FILE_LINK: &str = "fl";
const PRESENCE_ONLY: [&str; 4] = ["d", "dl", "bl", "p"];

pub(crate) fn hashable(stamp: &PathStamp) -> bool {
    stamp.kind == FILE || stamp.kind == FILE_LINK
}

fn presence_only(stamp: &PathStamp) -> bool {
    PRESENCE_ONLY.contains(&stamp.kind)
}

/// Each file's native content digest, or `None` where it cannot be read.
pub(crate) fn file_digests(paths: &[PathBuf]) -> Vec<Option<String>> {
    digest_files(paths)
        .into_iter()
        .map(|digest| match digest {
            Ok(digest) => Some(format!("{NATIVE_DIGEST_PREFIX}{}", hex_digest(&digest))),
            Err(_) => None,
        })
        .collect()
}

pub(crate) fn file_digest(path: &Path) -> Option<String> {
    file_digests(&[path.to_path_buf()]).pop().flatten()
}

pub(crate) fn is_racy(stamp: &PathStamp, snapshot_ns: i64, window_ns: i64) -> bool {
    hashable(stamp) && stamp.mtime_ns.max(stamp.ctime_ns) >= snapshot_ns - window_ns
}

fn by_path(stored: &[StoredProjectFile]) -> HashMap<&str, &StoredProjectFile> {
    stored
        .iter()
        .map(|file| (file.stamp.relative_path.as_str(), file))
        .collect()
}

fn same_identity(stamp: &PathStamp, recorded: &PathStamp) -> bool {
    stamp.kind == recorded.kind
        && stamp.link == recorded.link
        && (presence_only(stamp) || stamp.size == recorded.size)
}

/// Whether every project path is unchanged, hashing only where stat moved or may be racy.
pub(crate) fn compare_project_files(
    project_dir: &Path,
    stored: &[StoredProjectFile],
    current: &[PathStamp],
) -> (bool, HashMap<String, String>, usize) {
    let mut verified: HashMap<String, String> = HashMap::new();
    let mut read: usize = 0;
    if stored.len() != current.len() {
        return (false, verified, read);
    }
    let previous_by_path: HashMap<&str, &StoredProjectFile> = by_path(stored);
    for stamp in current {
        let Some(previous) = previous_by_path.get(stamp.relative_path.as_str()) else {
            return (false, verified, read);
        };
        if !same_identity(stamp, &previous.stamp) {
            return (false, verified, read);
        }
        if presence_only(stamp) || (*stamp == previous.stamp && !previous.racy) {
            continue;
        }
        let Some(previous_digest) = previous.digest.as_ref().filter(|_| hashable(stamp)) else {
            return (false, verified, read);
        };
        read += 1;
        match file_digest(&project_dir.join(&stamp.relative_path)) {
            Some(digest) if digest == *previous_digest => {
                let _ = verified.insert(stamp.relative_path.clone(), digest);
            }
            _ => return (false, verified, read),
        }
    }
    (true, verified, read)
}

/// Digests still valid for current files, without reading any content.
pub(crate) fn carried_forward_digests(
    stored: &[StoredProjectFile],
    current: &[PathStamp],
    verified: HashMap<String, String>,
) -> HashMap<String, String> {
    let previous_by_path: HashMap<&str, &StoredProjectFile> = by_path(stored);
    let mut digests: HashMap<String, String> = verified;
    for stamp in current {
        if digests.contains_key(&stamp.relative_path) {
            continue;
        }
        if let Some(previous) = previous_by_path.get(stamp.relative_path.as_str())
            && let Some(digest) = &previous.digest
            && !previous.racy
            && previous.stamp == *stamp
        {
            let _ = digests.insert(stamp.relative_path.clone(), digest.clone());
        }
    }
    digests
}

/// Hashable files whose stat identity moved since the stored compile.
pub(crate) fn restamped_paths(
    stored: &[StoredProjectFile],
    current: &[PathStamp],
) -> HashSet<String> {
    let previous_by_path: HashMap<&str, &StoredProjectFile> = by_path(stored);
    current
        .iter()
        .filter(|stamp| {
            hashable(stamp)
                && previous_by_path
                    .get(stamp.relative_path.as_str())
                    .is_some_and(|previous| {
                        previous.stamp.kind == stamp.kind && previous.stamp != **stamp
                    })
        })
        .map(|stamp| stamp.relative_path.clone())
        .collect()
}

/// Whether a hit verified any file by content, so its new stamp is worth storing.
pub(crate) fn needs_refresh(stored: &[StoredProjectFile], current: &[PathStamp]) -> bool {
    let previous_by_path: HashMap<&str, &StoredProjectFile> = by_path(stored);
    current.iter().any(|stamp| {
        previous_by_path
            .get(stamp.relative_path.as_str())
            .is_some_and(|previous| (previous.racy || previous.stamp != *stamp) && hashable(stamp))
    })
}

/// Each project path's stat identity with any digest already known for it.
pub(crate) fn stored_project_files(
    snapshot: &[PathStamp],
    digests: &HashMap<String, String>,
    snapshot_ns: i64,
    window_ns: i64,
) -> Vec<StoredProjectFile> {
    snapshot
        .iter()
        .map(|stamp| StoredProjectFile {
            stamp: stamp.clone(),
            digest: digests.get(&stamp.relative_path).cloned(),
            racy: is_racy(stamp, snapshot_ns, window_ns),
        })
        .collect()
}

/// The attempt's digests extended with racy files, plus `paths`, that still lack one.
pub(crate) fn with_missing_digests(
    attempt: &ReuseAttempt,
    paths: &HashSet<String>,
    window_ns: i64,
) -> HashMap<String, String> {
    let mut completed: HashMap<String, String> = attempt.digests.clone();
    let missing: Vec<&PathStamp> = attempt
        .snapshot
        .iter()
        .filter(|stamp| {
            hashable(stamp)
                && !completed.contains_key(&stamp.relative_path)
                && (paths.contains(&stamp.relative_path)
                    || is_racy(stamp, attempt.snapshot_ns, window_ns))
        })
        .collect();
    let files: Vec<PathBuf> = missing
        .iter()
        .map(|stamp| attempt.project_dir.join(&stamp.relative_path))
        .collect();
    for (stamp, digest) in missing.iter().zip(file_digests(&files)) {
        if let Some(digest) = digest {
            let _ = completed.insert(stamp.relative_path.clone(), digest);
        }
    }
    completed
}

/// Bytes hashing `paths` that still lack a digest would read.
pub(crate) fn pending_digest_bytes(
    snapshot: &[PathStamp],
    digests: &HashMap<String, String>,
    paths: &HashSet<String>,
) -> u64 {
    snapshot
        .iter()
        .filter(|stamp| paths.contains(&stamp.relative_path))
        .filter(|stamp| !digests.contains_key(&stamp.relative_path))
        .map(|stamp| stamp.size)
        .sum()
}
