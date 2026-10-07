//! Parsed MODEL header metadata whose leaves are the caller's own authored values.

/// One audit instance; every field holds the authored value Python would store.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ParsedAudit<N> {
    pub definition_name: N,
    pub arguments: Vec<(N, N)>,
    pub name: Option<N>,
    pub description: Option<N>,
    /// The authored severity text, which names one of the audit severities.
    pub severity: Option<N>,
    pub run_scope: Option<N>,
    /// The authored boolean, or `None` for Python's default of `False`.
    pub always_run: Option<N>,
    pub minimum_samples: Option<N>,
    pub evidence_limit: Option<N>,
}

/// One MODEL column.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ParsedColumn<N> {
    pub name: N,
    pub column_type: Option<N>,
    pub nullable: Option<N>,
    pub description: Option<N>,
    pub audits: Vec<ParsedAudit<N>>,
    pub migrate_from: Option<N>,
}

/// The MODEL header's columns and model-level audits.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct HeaderMetadata<N> {
    pub columns: Vec<ParsedColumn<N>>,
    pub audits: Vec<ParsedAudit<N>>,
}

/// Why Python must parse a header's metadata instead.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum HeaderMetadataDeferral {
    /// Python's parse raises; it runs to raise its exact error.
    Invalid,
    /// Python parses it with rules the native parser does not reproduce.
    Unsupported,
}
