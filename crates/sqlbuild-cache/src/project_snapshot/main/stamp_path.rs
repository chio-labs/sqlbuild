use std::path::Path;

use crate::project_snapshot::models::PathStamp;

/// `os.lstat` identity of one artifact path as a file stamp, or `None` when it is missing.
pub fn stamp_path(path: &Path) -> Option<PathStamp> {
    crate::project_snapshot::_helpers::stat::stamp_path(path)
}
