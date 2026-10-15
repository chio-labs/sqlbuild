//! Fitted, case-folded janitor archive names.

use crate::identifier_fitting::main::fit_artifact_logical_name::fit_artifact_logical_name;
use crate::janitor_planning::constants::{
    ARCHIVE_ARTIFACT_LABEL, ARCHIVE_NAME_PREFIX, ARCHIVE_NAME_SEPARATOR,
};
use crate::janitor_planning::models::ArchiveTimestamp;

/// The archive name keeping prefix, timestamp and kind intact; `Err` carries the fitting error.
pub fn build_archive_name(
    (original_name, archived_at): (&str, ArchiveTimestamp),
    identifier_limit: i64,
    kind: Option<&str>,
) -> Result<String, String> {
    let kind_segment: String = kind.map_or_else(String::new, |kind| {
        format!("{kind}{ARCHIVE_NAME_SEPARATOR}")
    });
    let fixed_prefix: String = format!(
        "{ARCHIVE_NAME_PREFIX}{:04}{:02}{:02}T{:02}{:02}{:02}Z{ARCHIVE_NAME_SEPARATOR}{kind_segment}",
        archived_at.year,
        archived_at.month,
        archived_at.day,
        archived_at.hour,
        archived_at.minute,
        archived_at.second,
    );
    let logical_part: String = fit_artifact_logical_name(
        (original_name, &fixed_prefix),
        identifier_limit,
        ARCHIVE_ARTIFACT_LABEL,
    )?;
    Ok(format!("{fixed_prefix}{logical_part}").to_lowercase())
}
