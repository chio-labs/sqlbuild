use std::path::{Path, PathBuf};
use std::time::{Duration, SystemTime};

use crate::compute_logs::models::CaptureStart;

pub(crate) fn capture_start(root: &Path, offset_seconds: u64) -> CaptureStart {
    CaptureStart {
        root: root.to_path_buf(),
        command: "compile".to_owned(),
        project_dir: "/project".to_owned(),
        target: None,
        started_at: SystemTime::now() - Duration::from_secs(offset_seconds),
    }
}

pub(crate) fn complete_captures(root: &Path) -> Vec<PathBuf> {
    let mut found: Vec<PathBuf> = Vec::new();
    for date in std::fs::read_dir(root).into_iter().flatten().flatten() {
        for capture in std::fs::read_dir(date.path())
            .into_iter()
            .flatten()
            .flatten()
        {
            found.extend(Some(capture.path()).filter(|path| path.join("complete").is_file()));
        }
    }
    found
}
