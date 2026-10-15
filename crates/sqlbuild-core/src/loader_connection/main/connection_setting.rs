//! `connection_setting`: one stripped string connection setting.

use crate::loader_connection::models::LoaderConnection;
use crate::text::main::python_strip::python_strip;

/// The stripped string setting `key`, or `None` when unset, not a string or blank.
#[must_use]
pub fn connection_setting<'a>(connection: &'a LoaderConnection, key: &str) -> Option<&'a str> {
    connection
        .strings
        .get(key)
        .map(|value| python_strip(value))
        .filter(|value| !value.is_empty())
}
