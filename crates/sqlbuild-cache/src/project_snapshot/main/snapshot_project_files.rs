use std::path::Path;

use crate::project_snapshot::models::{PathStamp, SnapshotRules};

/// Stat every compile-relevant path under `project_dir`, or `None` to let Python walk it.
pub fn snapshot_project_files(project_dir: &Path, rules: &SnapshotRules) -> Option<Vec<PathStamp>> {
    #[cfg(unix)]
    {
        crate::project_snapshot::_helpers::walk::snapshot(project_dir, rules)
    }
    #[cfg(not(unix))]
    {
        let _ = (project_dir, rules);
        None
    }
}
