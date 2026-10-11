//! Stat identity of the artifacts a compile leaves in target/.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

use crate::project_reuse::_helpers::files::file_digest;
use crate::project_reuse::models::{CompileRecord, RecordedArtifact, ReuseRules};
use crate::project_snapshot::main::stamp_path::stamp_path;
use crate::project_snapshot::models::PathStamp;

type Stamps = BTreeMap<String, PathStamp>;

fn path_stamp(path: &str) -> Option<PathStamp> {
    let mut stamp: PathStamp = stamp_path(Path::new(path))?;
    path.clone_into(&mut stamp.relative_path);
    Some(stamp)
}

fn compiled_root(project_dir: &Path, rules: &ReuseRules) -> PathBuf {
    project_dir.join(&rules.compiled_root)
}

/// Stat every compiled artifact plus `extra_paths`, keyed by path.
fn snapshot_target_files(project_dir: &Path, extra_paths: &[&str], rules: &ReuseRules) -> Stamps {
    let mut stamps: Stamps = BTreeMap::new();
    let mut pending: Vec<PathBuf> = vec![compiled_root(project_dir, rules)];
    while let Some(directory) = pending.pop() {
        let Ok(entries) = std::fs::read_dir(&directory) else {
            continue;
        };
        for entry in entries.flatten() {
            let path: PathBuf = entry.path();
            if entry.file_type().is_ok_and(|kind| kind.is_dir()) {
                pending.push(path);
                continue;
            }
            let path: String = path.to_string_lossy().into_owned();
            if let Some(stamp) = path_stamp(&path) {
                let _ = stamps.insert(path, stamp);
            }
        }
    }
    for path in extra_paths {
        if let Some(stamp) = path_stamp(path) {
            let _ = stamps.insert((*path).to_owned(), stamp);
        }
    }
    stamps
}

fn keyed_stamp(path: &str) -> Option<(String, PathStamp)> {
    let stamp: PathStamp = path_stamp(path)?;
    Some((path.to_owned(), stamp))
}

/// The whole compiled tree plus extra paths, or only the given paths.
fn target_stamps(project_dir: &Path, paths: &[&str], tree: bool, rules: &ReuseRules) -> Stamps {
    if !tree {
        return paths.iter().copied().filter_map(keyed_stamp).collect();
    }
    let prefix: String = compiled_prefix(project_dir, rules);
    let extra: Vec<&str> = paths
        .iter()
        .copied()
        .filter(|path| !path.starts_with(prefix.as_str()))
        .collect();
    snapshot_target_files(project_dir, &extra, rules)
}

fn compiled_prefix(project_dir: &Path, rules: &ReuseRules) -> String {
    format!(
        "{}{}",
        compiled_root(project_dir, rules).to_string_lossy(),
        std::path::MAIN_SEPARATOR
    )
}

fn matches_recorded(
    stamp: &PathStamp,
    artifact: &RecordedArtifact,
    since_ns: i64,
    rules: &ReuseRules,
) -> bool {
    match artifact {
        RecordedArtifact::Kept { size, mtime_ns } => {
            stamp.size == *size && stamp.mtime_ns == *mtime_ns
        }
        RecordedArtifact::Written { digest } => {
            stamp.mtime_ns.max(stamp.ctime_ns) < since_ns - rules.racy_window_ns
                || file_digest(Path::new(&stamp.relative_path)).as_deref() == Some(digest)
        }
    }
}

/// Stamp this compile's artifacts, or `None` when any changed since it wrote them.
pub(crate) fn verified_target_files(
    project_dir: &Path,
    record: &CompileRecord,
    since_ns: i64,
    rules: &ReuseRules,
) -> Option<Vec<PathStamp>> {
    let prefix: String = compiled_prefix(project_dir, rules);
    let dag_path: Option<&str> = record.dag_path.as_deref();
    let written: bool = record.artifacts_written;
    let expected: BTreeMap<&str, &RecordedArtifact> = record
        .artifacts
        .iter()
        .filter(|(path, _)| path.starts_with(prefix.as_str()) || Some(path.as_str()) == dag_path)
        .map(|(path, artifact)| (path.as_str(), artifact))
        .collect();
    let paths: Vec<&str> = expected.keys().copied().collect();
    let stamps: Stamps = target_stamps(project_dir, &paths, written, rules);
    let keys_match: bool = stamps.len() == expected.len()
        && stamps
            .keys()
            .all(|path| expected.contains_key(path.as_str()));
    if !keys_match
        || !stamps
            .iter()
            .all(|(path, stamp)| matches_recorded(stamp, expected[path.as_str()], since_ns, rules))
    {
        return None;
    }
    if target_stamps(project_dir, &paths, written, rules) != stamps {
        return None;
    }
    Some(stamps.into_values().collect())
}

/// Whether every stored artifact is unchanged and, for a written tree, none was added.
pub(crate) fn target_files_unchanged(
    stored: &[PathStamp],
    project_dir: &Path,
    tree: bool,
    rules: &ReuseRules,
) -> bool {
    let paths: Vec<&str> = stored
        .iter()
        .map(|stamp| stamp.relative_path.as_str())
        .collect();
    let expected: Stamps = stored
        .iter()
        .map(|stamp| (stamp.relative_path.clone(), stamp.clone()))
        .collect();
    target_stamps(project_dir, &paths, tree, rules) == expected
}
