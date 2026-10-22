//! Where the base snapshot is cached, what its cache key covers, and how old entries are pruned.

use std::collections::BTreeSet;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use sqlbuild_analysis::definition_changes::main::definition_digest::definition_digest;
use sqlbuild_rules::constants::NATIVE_BUILD_IDENTITY;

use crate::bindings::_helpers::change_selection::fingerprints::{
    environment_digest, referenced_environment,
};

/// Cached base snapshots kept per project; older ones are removed after each compile.
const KEPT_SNAPSHOTS: usize = 8;
const SNAPSHOT_SUFFIX: &str = "json";
/// Authored file types that can read environment variables through SQL or configuration.
const AUTHORED_SUFFIXES: [&str; 5] = ["toml", "yml", "yaml", "sql", "py"];
/// Directories of build output, tools and dependencies, never authored project files.
const SKIPPED_DIRECTORIES: [&str; 4] = ["target", "logs", "node_modules", "__pycache__"];

/// Authored files below `directory`, skipping hidden, build and dependency directories.
fn authored_files(directory: &Path) -> std::io::Result<Vec<PathBuf>> {
    let mut files: Vec<PathBuf> = Vec::new();
    let mut pending: Vec<PathBuf> = vec![directory.to_path_buf()];
    while let Some(next) = pending.pop() {
        for entry in std::fs::read_dir(&next)? {
            let path: PathBuf = entry?.path();
            let name: String = path
                .file_name()
                .map(|name| name.to_string_lossy().into_owned())
                .unwrap_or_default();
            if name.starts_with('.') {
                continue;
            }
            if path.is_dir() {
                if !SKIPPED_DIRECTORIES.contains(&name.as_str()) {
                    pending.push(path);
                }
            } else if path
                .extension()
                .is_some_and(|suffix| AUTHORED_SUFFIXES.contains(&&*suffix.to_string_lossy()))
            {
                files.push(path);
            }
        }
    }
    files.sort();
    Ok(files)
}

/// The digest of every environment variable the project's files read, by its current value.
fn environment_inputs(project_dir: &Path) -> std::io::Result<String> {
    let mut names: BTreeSet<String> = BTreeSet::new();
    for file in authored_files(project_dir)? {
        let bytes: Vec<u8> = std::fs::read(&file)?;
        names.extend(referenced_environment(&String::from_utf8_lossy(&bytes)));
    }
    Ok(environment_digest(&names))
}

/// The cache key of a base compile besides its commit: build, target, vars, local config, env.
pub(crate) fn cache_key(
    project_dir: &Path,
    (target, vars, local_config): (Option<&str>, &str, &str),
) -> std::io::Result<String> {
    Ok(definition_digest(&[
        NATIVE_BUILD_IDENTITY,
        target.unwrap_or_default(),
        vars,
        local_config,
        &environment_inputs(project_dir)?,
    ]))
}

/// A work directory name no other run, even one reusing this process id, can choose.
pub(crate) fn work_directory_name(short: &str) -> String {
    let nanos: u128 = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_or(0, |elapsed| elapsed.as_nanos());
    format!("work-{short}-{}-{nanos:x}", std::process::id())
}

/// Remove all but the newest cached base snapshots in `cache_dir`.
pub(crate) fn prune_snapshots(cache_dir: &Path) -> std::io::Result<()> {
    let mut snapshots: Vec<(SystemTime, PathBuf)> = Vec::new();
    for entry in std::fs::read_dir(cache_dir)? {
        let path: PathBuf = entry?.path();
        if path.is_file()
            && path
                .extension()
                .is_some_and(|suffix| suffix == SNAPSHOT_SUFFIX)
        {
            snapshots.push((std::fs::metadata(&path)?.modified()?, path));
        }
    }
    snapshots.sort_by(|left, right| right.cmp(left));
    for (_, path) in snapshots.into_iter().skip(KEPT_SNAPSHOTS) {
        match std::fs::remove_file(&path) {
            Ok(()) => {}
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(error) => return Err(error),
        }
    }
    Ok(())
}
