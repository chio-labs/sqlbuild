//! Inputs of one ingestr command line.

use std::collections::BTreeMap;

/// The adapter connection settings an ingestr destination URI reads.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct IngestrConnection {
    /// Connection settings whose values are Python strings, unstripped.
    pub strings: BTreeMap<String, String>,
    /// `str(connection["port"])` when the connection sets a port.
    pub port: Option<String>,
}

/// A resolved ingestr source configuration.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct IngestrSource {
    pub source_uri: String,
    pub source_table: String,
    pub strategy: Option<String>,
    pub incremental_key: Option<String>,
    pub primary_key: Vec<String>,
    pub columns: Option<String>,
    pub extra_args: Vec<String>,
}

/// Where one ingestr run writes.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct IngestrDestination {
    pub uri: String,
    pub table: String,
    /// The run rebuilds the destination from scratch.
    pub is_reload: bool,
}
