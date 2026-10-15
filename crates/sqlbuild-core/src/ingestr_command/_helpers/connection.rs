//! Connection settings read the way the ingestr destination expects them.

use crate::ingestr_command::constants::INGESTR_LOADER;
use crate::ingestr_command::errors::IngestrCommandError;
use crate::loader_connection::main::connection_setting::connection_setting;
use crate::loader_connection::main::required_connection_setting::required_connection_setting;
use crate::loader_connection::models::LoaderConnection;

/// The stripped string setting `key`, or `None` when unset, not a string or blank.
pub(crate) fn optional<'a>(connection: &'a LoaderConnection, key: &str) -> Option<&'a str> {
    connection_setting(connection, key)
}

/// The stripped string setting `key`, which the adapter's ingestr destination requires.
pub(crate) fn required<'a>(
    connection: &'a LoaderConnection,
    key: &str,
    adapter_name: &str,
) -> Result<&'a str, IngestrCommandError> {
    required_connection_setting(connection, key, adapter_name, INGESTR_LOADER)
        .map_err(|message| IngestrCommandError { message })
}

/// `(key, value)` when the setting `key` is set.
fn setting<'a>(connection: &'a LoaderConnection, key: &'a str) -> Option<(&'a str, &'a str)> {
    optional(connection, key).map(|value| (key, value))
}

/// The settings among `keys` that are set, in `keys` order.
pub(crate) fn present<'a>(
    connection: &'a LoaderConnection,
    keys: &[&'a str],
) -> Vec<(&'a str, &'a str)> {
    keys.iter()
        .filter_map(|key| setting(connection, key))
        .collect()
}
