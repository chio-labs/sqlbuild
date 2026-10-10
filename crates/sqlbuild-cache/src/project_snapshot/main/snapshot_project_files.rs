use std::path::Path;

use crate::project_snapshot::models::{PathStamp, SnapshotRules};

/// Stat every compile-relevant path under `project_dir`, in walk order.
pub fn snapshot_project_files(project_dir: &Path, rules: &SnapshotRules) -> Vec<PathStamp> {
    crate::project_snapshot::_helpers::walk::snapshot(project_dir, rules)
}
