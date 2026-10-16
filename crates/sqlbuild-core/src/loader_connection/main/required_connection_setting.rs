//! `required_connection_setting`: one connection setting a loader destination requires.

use crate::loader_connection::main::connection_setting::connection_setting;
use crate::loader_connection::models::LoaderConnection;

/// The stripped string setting `key`, which the adapter's `loader` destination requires.
pub fn required_connection_setting<'a>(
    connection: &'a LoaderConnection,
    key: &str,
    adapter_name: &str,
    loader: &str,
) -> Result<&'a str, String> {
    connection_setting(connection, key).ok_or_else(|| {
        format!(
            "Adapter '{adapter_name}' requires connection.{key} for {loader} integration loaders"
        )
    })
}
