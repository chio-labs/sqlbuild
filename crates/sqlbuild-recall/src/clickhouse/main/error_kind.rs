//! `error_kind`: what a ClickHouse failure means for Recall delivery.

use crate::clickhouse::_helpers::digits::leading_number;
use crate::clickhouse::constants::{
    PERMISSION_CODES, SERVER_CODE_MARKERS, TRANSIENT_CODES, UNKNOWN_DATABASE_CODE,
};
use crate::store::errors::StoreErrorKind;

/// The kind of a client failure from its message: permission codes deny the store, transient codes and failures without a server code (network, timeouts) are retried, an unknown database is reported as such.
#[must_use]
pub fn error_kind(message: &str) -> StoreErrorKind {
    let code: Option<u64> = SERVER_CODE_MARKERS.iter().find_map(|marker| {
        let start: usize = message.find(marker)? + marker.len();
        leading_number(&message[start..])
    });
    let Some(code) = code else {
        return StoreErrorKind::Busy;
    };
    if PERMISSION_CODES.contains(&code) {
        StoreErrorKind::Permission
    } else if TRANSIENT_CODES.contains(&code) {
        StoreErrorKind::Busy
    } else if code == UNKNOWN_DATABASE_CODE {
        StoreErrorKind::NotFound
    } else {
        StoreErrorKind::Other
    }
}
