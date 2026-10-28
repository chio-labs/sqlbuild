//! Stat identity of the artifacts a compile leaves in target/.

use std::collections::{BTreeMap, HashMap};
use std::path::{Path, PathBuf};

use crate::project_reuse::_helpers::files::file_digest;
use crate::project_reuse::constants::FAILED_COMPILED_DIRECTORY_NAME;
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

/// The failed-compile directory beside the compiled directory.
fn failed_root(project_dir: &Path, rules: &ReuseRules) -> PathBuf {
    compiled_root(project_dir, rules).with_file_name(FAILED_COMPILED_DIRECTORY_NAME)
}

/// Stat every compiled and failed-compile artifact plus `extra_paths`, keyed by path.
fn snapshot_target_files(project_dir: &Path, extra_paths: &[&str], rules: &ReuseRules) -> Stamps {
    let mut stamps: Stamps = BTreeMap::new();
    let mut pending: Vec<PathBuf> = vec![
        compiled_root(project_dir, rules),
        failed_root(project_dir, rules),
    ];
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
    let prefixes: [String; 2] = tree_prefixes(project_dir, rules);
    let extra: Vec<&str> = paths
        .iter()
        .copied()
        .filter(|path| !in_trees(path, &prefixes))
        .collect();
    snapshot_target_files(project_dir, &extra, rules)
}

/// The compiled and failed-compile directories, each with a trailing separator.
fn tree_prefixes(project_dir: &Path, rules: &ReuseRules) -> [String; 2] {
    [
        compiled_root(project_dir, rules),
        failed_root(project_dir, rules),
    ]
    .map(|root| format!("{}{}", root.to_string_lossy(), std::path::MAIN_SEPARATOR))
}

/// Whether `path` is under one of the `prefixes` directories.
fn in_trees(path: &str, prefixes: &[String]) -> bool {
    prefixes
        .iter()
        .any(|prefix| path.starts_with(prefix.as_str()))
}

/// Whether `stamp` shows what this compile left there, and whether that read its content.
fn matches_recorded(
    stamp: &PathStamp,
    artifact: &RecordedArtifact,
    since_ns: i64,
    rules: &ReuseRules,
) -> (bool, bool) {
    match artifact {
        RecordedArtifact::Kept { size, mtime_ns } => {
            (stamp.size == *size && stamp.mtime_ns == *mtime_ns, false)
        }
        RecordedArtifact::Written { digest } => {
            if stamp.mtime_ns.max(stamp.ctime_ns) < since_ns - rules.racy_window_ns {
                return (true, false);
            }
            let read: Option<String> = file_digest(Path::new(&stamp.relative_path));
            (read.as_deref() == Some(digest), true)
        }
    }
}

/// Each expected artifact's stamp: vouched when kept as vouched for, otherwise read.
fn vouched_stamps(expected: &BTreeMap<&str, &RecordedArtifact>, vouched: &[PathStamp]) -> Stamps {
    let vouched: HashMap<&str, &PathStamp> = vouched
        .iter()
        .map(|stamp| (stamp.relative_path.as_str(), stamp))
        .collect();
    expected
        .iter()
        .filter_map(|(path, artifact)| match artifact {
            RecordedArtifact::Kept { size, mtime_ns } => match vouched.get(path) {
                Some(stamp) if stamp.size == *size && stamp.mtime_ns == *mtime_ns => {
                    Some(((*path).to_owned(), (*stamp).clone()))
                }
                _ => keyed_stamp(path),
            },
            RecordedArtifact::Written { .. } => keyed_stamp(path),
        })
        .collect()
}

/// Stamp this compile's artifacts, or `None` when any changed since it wrote them.
pub(crate) fn verified_target_files(
    project_dir: &Path,
    record: &CompileRecord,
    since_ns: i64,
    rules: &ReuseRules,
) -> Option<Vec<PathStamp>> {
    let prefixes: [String; 2] = tree_prefixes(project_dir, rules);
    let dag_path: Option<&str> = record.dag_path.as_deref();
    let written: bool = record.artifacts_written;
    let expected: BTreeMap<&str, &RecordedArtifact> = record
        .artifacts
        .iter()
        .filter(|(path, _)| in_trees(path, &prefixes) || Some(path.as_str()) == dag_path)
        .map(|(path, artifact)| (path.as_str(), artifact))
        .collect();
    let paths: Vec<&str> = expected.keys().copied().collect();
    let stamps: Stamps = match &record.vouched_target_stamps {
        Some(vouched) => vouched_stamps(&expected, vouched),
        None => target_stamps(project_dir, &paths, written, rules),
    };
    let keys_match: bool = stamps.len() == expected.len()
        && stamps
            .keys()
            .all(|path| expected.contains_key(path.as_str()));
    if !keys_match {
        return None;
    }
    let mut read_paths: Vec<&str> = Vec::new();
    for (path, stamp) in &stamps {
        let (matched, read) = matches_recorded(stamp, expected[path.as_str()], since_ns, rules);
        if !matched {
            return None;
        }
        if read {
            read_paths.push(path.as_str());
        }
    }
    for path in read_paths {
        let restamped: Option<PathStamp> = path_stamp(path);
        if restamped.as_ref() != stamps.get(path) {
            return None;
        }
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
