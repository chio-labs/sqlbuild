//! The stored column list.

use crate::fingerprint_storage::constants::FINGERPRINT_COLUMNS;

/// Every stored column, comma separated.
pub(crate) fn column_list() -> String {
    FINGERPRINT_COLUMNS.join(", ")
}
