/// Line, column, end line and end column.
pub(super) type Span = (usize, usize, usize, usize);

/// A located name.
pub(super) type Located = (String, Span);

/// The parsed query and locations, or the failure message and help.
pub(super) type ModelSummary =
    Result<(String, Vec<Located>, Vec<Located>), (String, Option<String>)>;

pub(super) struct ModelFileTestCase {
    pub(super) description: &'static str,
    pub(super) contents: &'static str,
    pub(super) expected_summary: ModelSummary,
}

/// A model whose `tags` header value nests `depth` lists deep.
pub(super) struct DeepModelHeaderTestCase {
    pub(super) description: &'static str,
    pub(super) depth: usize,
    pub(super) expected_summary: ModelSummary,
}

/// A model header and what its native header facts must read, as Python reads the header.
pub(super) struct HeaderFactsTestCase {
    pub(super) description: &'static str,
    pub(super) contents: &'static str,
    /// `(key, template, macro path, blocks reuse)` of each header entry, in dict order.
    pub(super) expected_entries: Vec<(&'static str, bool, Option<Vec<&'static str>>, bool)>,
    /// `(name, type, nullable, description, audit definitions)` of each column, or `None`.
    pub(super) expected_columns: Option<Vec<ColumnSummary>>,
}

/// `(name, type, nullable, description, audit definitions)` of one parsed column.
pub(super) type ColumnSummary = (
    &'static str,
    Option<&'static str>,
    Option<bool>,
    Option<&'static str>,
    Vec<&'static str>,
);
