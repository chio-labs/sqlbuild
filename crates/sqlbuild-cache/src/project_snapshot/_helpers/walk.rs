//! Python's `snapshot_project_files` walk over `os.scandir`, `os.readlink` and `os.stat`.

use std::collections::HashSet;
use std::fs::Metadata;
use std::path::{Path, PathBuf};

use crate::project_snapshot::_helpers::path_text::path_text;
use crate::project_snapshot::_helpers::stat::{file_identity, stat_times};
use crate::project_snapshot::models::{PathStamp, SnapshotRules};

const FILE: &str = "f";
const FILE_LINK: &str = "fl";
const DIRECTORY: &str = "d";
const DIRECTORY_LINK: &str = "dl";
const BROKEN_LINK: &str = "bl";
const SPECIAL: &str = "s";
const PRESENCE: &str = "p";

/// Every stamped path in walk order; names that are not UTF-8 keep their exact bytes escaped.
pub(crate) fn snapshot(project_dir: &Path, rules: &SnapshotRules) -> Vec<PathStamp> {
    let mut stamps: Vec<PathStamp> = Vec::new();
    let mut visited: HashSet<PathBuf> = HashSet::from([real_path(project_dir)]);
    let mut pending: Vec<(PathBuf, bool)> = vec![(project_dir.to_path_buf(), true)];
    while let Some((directory, is_root)) = pending.pop() {
        let Ok(entries) = std::fs::read_dir(&directory) else {
            continue;
        };
        for entry in entries.flatten() {
            let path: PathBuf = entry.path();
            let file_name = entry.file_name();
            let name: String = path_text(&file_name);
            let Ok(relative) = path.strip_prefix(project_dir) else {
                continue;
            };
            let relative_path: String = path_text(relative.as_os_str());
            let Some(stamp) = entry_stamp(&path, &name, is_root, rules) else {
                continue;
            };
            if stamp.kind == DIRECTORY
                || (stamp.kind == DIRECTORY_LINK && visited.insert(real_path(&path)))
            {
                pending.push((path, false));
            }
            stamps.push(PathStamp {
                relative_path,
                ..stamp
            });
        }
    }
    stamps
}

fn real_path(path: &Path) -> PathBuf {
    std::fs::canonicalize(path).unwrap_or_else(|_| path.to_path_buf())
}

/// The entry's stamp, or `None` to skip it.
fn entry_stamp(path: &Path, name: &str, is_root: bool, rules: &SnapshotRules) -> Option<PathStamp> {
    let Ok(metadata) = std::fs::symlink_metadata(path) else {
        return None;
    };
    if metadata.file_type().is_symlink() {
        return link_stamp(path, name, is_root, rules);
    }
    if metadata.is_dir() {
        return (!excluded(name, is_root, rules)).then(|| marker(DIRECTORY, None));
    }
    if rules
        .presence_suffixes
        .iter()
        .any(|suffix| name.ends_with(suffix.as_str()))
    {
        return Some(marker(PRESENCE, None));
    }
    if file_identity(&metadata).is_some_and(|identity| rules.output_files.contains(&identity)) {
        return Some(marker(PRESENCE, None));
    }
    Some(file_stamp(&metadata, None))
}

fn link_stamp(path: &Path, name: &str, is_root: bool, rules: &SnapshotRules) -> Option<PathStamp> {
    let Ok(target) = std::fs::read_link(path) else {
        return None;
    };
    let link: String = path_text(target.as_os_str());
    let Ok(metadata) = std::fs::metadata(path) else {
        return Some(marker(BROKEN_LINK, Some(link)));
    };
    if !metadata.is_dir() {
        return Some(file_stamp(&metadata, Some(link)));
    }
    if excluded(name, is_root, rules) {
        return None;
    }
    Some(marker(DIRECTORY_LINK, Some(link)))
}

fn excluded(name: &str, is_root: bool, rules: &SnapshotRules) -> bool {
    rules.excluded.iter().any(|excluded| excluded == name)
        || (is_root && rules.excluded_root.iter().any(|excluded| excluded == name))
}

fn marker(kind: &'static str, link: Option<String>) -> PathStamp {
    PathStamp {
        relative_path: String::new(),
        kind,
        size: 0,
        mtime_ns: 0,
        ctime_ns: 0,
        inode: 0,
        link,
    }
}

fn file_stamp(metadata: &Metadata, link: Option<String>) -> PathStamp {
    let kind: &'static str = match (metadata.is_file(), link.is_some()) {
        (true, false) => FILE,
        (true, true) => FILE_LINK,
        (false, _) => SPECIAL,
    };
    let (mtime_ns, ctime_ns) = stat_times(metadata);
    PathStamp {
        relative_path: String::new(),
        kind,
        size: metadata.len(),
        mtime_ns,
        ctime_ns,
        inode: file_identity(metadata).map_or(0, |(_, inode)| inode),
        link,
    }
}
