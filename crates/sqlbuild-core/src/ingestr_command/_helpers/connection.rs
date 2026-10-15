//! Connection settings read the way the ingestr destination expects them.

use crate::ingestr_command::errors::IngestrCommandError;
use crate::ingestr_command::models::IngestrConnection;
use crate::text::main::python_strip::python_strip;

/// The stripped string setting `key`, or `None` when unset, not a string or blank.
pub(crate) fn optional<'a>(connection: &'a IngestrConnection, key: &str) -> Option<&'a str> {
    connection
        .strings
        .get(key)
        .map(|value| python_strip(value))
        .filter(|value| !value.is_empty())
}

/// The stripped string setting `key`, which the adapter's destination requires.
pub(crate) fn required<'a>(
    connection: &'a IngestrConnection,
    key: &str,
    adapter_name: &str,
) -> Result<&'a str, IngestrCommandError> {
    optional(connection, key).ok_or_else(|| IngestrCommandError {
        message: format!(
            "Adapter '{adapter_name}' requires connection.{key} for ingestr integration loaders"
        ),
    })
}

/// `(key, value)` when the setting `key` is set.
fn setting<'a>(connection: &'a IngestrConnection, key: &'a str) -> Option<(&'a str, &'a str)> {
    optional(connection, key).map(|value| (key, value))
}

/// The settings among `keys` that are set, in `keys` order.
pub(crate) fn present<'a>(
    connection: &'a IngestrConnection,
    keys: &[&'a str],
) -> Vec<(&'a str, &'a str)> {
    keys.iter()
        .filter_map(|key| setting(connection, key))
        .collect()
}
