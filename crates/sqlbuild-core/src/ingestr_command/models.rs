//! Inputs of one ingestr command line.

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
