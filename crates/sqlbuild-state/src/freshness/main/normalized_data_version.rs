//! `normalized_data_version`: a data version as stable state text.

use crate::freshness::constants::UTC_SUFFIX;
use crate::freshness::models::DataVersion;

/// A timestamp's `isoformat()`, an integer's digits, or the text itself.
#[must_use]
pub fn normalized_data_version(value: &DataVersion) -> String {
    let (local, utc) = match value {
        DataVersion::Timestamp { local, utc } => (local, *utc),
        DataVersion::Integer(text) | DataVersion::Text(text) => return text.clone(),
    };
    let date = &local.date;
    let mut text: String = format!(
        "{:04}-{:02}-{:02}T{:02}:{:02}:{:02}",
        date.year, date.month, date.day, local.hour, local.minute, local.second
    );
    if local.microsecond != 0 {
        text.push_str(&format!(".{:06}", local.microsecond));
    }
    if utc {
        text.push_str(UTC_SUFFIX);
    }
    text
}
