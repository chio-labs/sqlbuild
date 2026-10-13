//! Fingerprint rows, read narrowing and latest-row indexes.

/// One fingerprint row to insert, with its timestamp already in ISO format.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct StoredFingerprint {
    pub node_type: String,
    pub node_name: String,
    pub target_database: Option<String>,
    pub target_schema: Option<String>,
    pub target_name: Option<String>,
    pub run_id: String,
    pub definition_hash: String,
    pub version_hash: String,
    pub schema_fingerprint: String,
    pub definition: String,
    pub metadata_json: String,
    pub ts: String,
}

/// How a latest-fingerprint read is narrowed to the relevant nodes.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum RelevantRead {
    /// Read every latest row with this SQL.
    Sql(String),
    /// Nothing can match; skip the read.
    Empty,
}

/// One latest fingerprint's identity.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct FingerprintIdentity<'a> {
    pub node_type: &'a str,
    pub node_name: &'a str,
}

/// Positions of the latest rows kept per node name and per identity, in Python dict order.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct LatestIndex {
    pub by_name: Vec<usize>,
    pub by_identity: Vec<usize>,
}
