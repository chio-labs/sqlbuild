//! Read launch records and turn their rules into the native reuse check's request.

use std::path::{Path, PathBuf};
use std::time::UNIX_EPOCH;

use sqlbuild_cache::project_reuse::models::{HostIdentity, ReuseRules};
use sqlbuild_cache::project_snapshot::models::SnapshotRules;

use crate::replay::constants::LAUNCH_RECORD_FORMAT;
use crate::replay::models::{LaunchRecord, LaunchRules};

/// The record at `path` for `key`, or `None` when absent, unreadable or of another shape.
pub(crate) fn read_record(path: &Path, key: &str) -> Option<LaunchRecord> {
    let Ok(bytes) = std::fs::read(path) else {
        return None;
    };
    let Ok(record) = serde_json::from_slice::<LaunchRecord>(&bytes) else {
        return None;
    };
    (record.format == LAUNCH_RECORD_FORMAT && record.key == key && startup_unchanged(&record))
        .then_some(record)
}

fn startup_unchanged(record: &LaunchRecord) -> bool {
    record
        .startup_inputs
        .iter()
        .all(|(path, modified, size)| match std::fs::metadata(path) {
            Ok(metadata) => {
                let Ok(time) = metadata.modified() else {
                    return false;
                };
                let Ok(duration) = time.duration_since(UNIX_EPOCH) else {
                    return false;
                };
                let Ok(current) = i64::try_from(duration.as_nanos()) else {
                    return false;
                };
                Some(current) == *modified && Some(metadata.len()) == *size
            }
            Err(error) => {
                error.kind() == std::io::ErrorKind::NotFound && modified.is_none() && size.is_none()
            }
        })
}

/// The native reuse rules of a record, with this process's redirected output files.
pub(crate) fn reuse_rules(rules: &LaunchRules, output_files: Vec<(u64, u64)>) -> ReuseRules {
    ReuseRules {
        snapshot: SnapshotRules {
            excluded: rules.excluded.clone(),
            excluded_root: rules.excluded_root.clone(),
            presence_suffixes: rules.presence_suffixes.clone(),
            output_files,
        },
        tracked_prefixes: rules.tracked_prefixes.clone(),
        untracked_names: rules.untracked_names.clone(),
        disabling_variables: rules.disabling_variables.clone(),
        config_filenames: rules.config_filenames.clone(),
        racy_window_ns: rules.racy_window_ns,
        max_stored_entries: rules.max_stored_entries,
        max_entry_bytes: rules.max_entry_bytes,
        missing_environment_value: rules.missing_environment_value.clone(),
        missing_file_digest: rules.missing_file_digest.clone(),
        missing_path_mtime_ns: rules.missing_path_mtime_ns,
        project_root_path_mtime_ns: rules.project_root_path_mtime_ns,
        compiled_root: PathBuf::from(&rules.compiled_root),
        retired_directories: rules.retired_directories.clone(),
    }
}

/// The host identity the Python process computed for this invocation.
pub(crate) fn host_identity(record: &LaunchRecord) -> HostIdentity {
    HostIdentity {
        invocation_digest: record.invocation_digest.clone(),
        runtime: record.runtime.clone(),
        search_path: record.search_path.clone(),
    }
}

/// `reuse_timings(outcome=HIT, check_ms)` plus `total_ms`, in Python's insertion order.
pub(crate) fn hit_timings(
    record: &LaunchRecord,
    check_ms: i64,
    total_ms: i64,
) -> Vec<(String, i64)> {
    let names = &record.timings;
    vec![
        (names.hit.clone(), 1),
        (names.miss.clone(), 0),
        (names.bypass.clone(), 0),
        (names.check.clone(), check_ms),
        (names.total.clone(), total_ms),
    ]
}
