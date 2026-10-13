//! The timestamp parsing a caller supplies for stored data versions.

use sqlbuild_cursor::algebra::models::LocalDateTime;

use crate::freshness::errors::FreshnessError;

/// Parses stored timestamp text into UTC wall time.
pub trait TimestampParser {
    /// `datetime.fromisoformat(text)` in UTC, naive text read as UTC.
    fn utc_timestamp(&self, text: &str) -> Result<LocalDateTime, FreshnessError>;
}
