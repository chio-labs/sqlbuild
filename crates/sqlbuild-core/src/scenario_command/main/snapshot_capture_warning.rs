//! The warning shown before committable snapshot files are written.

/// Review guidance for captured snapshots, noting when size limits are bypassed.
#[must_use]
pub fn snapshot_capture_warning(force: bool) -> String {
    let suffix: &str = if force {
        " Size limits are bypassed."
    } else {
        ""
    };
    format!(
        "Review captured scenario snapshots before committing; they may contain sensitive \
         warehouse data.{suffix}"
    )
}
