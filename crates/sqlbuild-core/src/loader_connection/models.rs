//! The adapter connection settings a loader destination reads.

use std::collections::BTreeMap;

/// The adapter connection settings an ingestr or dlt destination reads.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct LoaderConnection {
    /// Connection settings whose values are Python strings, unstripped.
    pub strings: BTreeMap<String, String>,
    /// `str(connection["port"])` when the connection sets a port.
    pub port: Option<String>,
}
