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
    pub(super) expected_entries: Vec<EntrySummary<'static>>,
    pub(super) expected_columns: Option<Vec<ColumnSummary<'static>>>,
}

/// `(key, template, macro path, blocks reuse)` of one header entry.
pub(super) type EntrySummary<'a> = (&'a str, bool, Option<Vec<&'a str>>, bool);

/// `(name, type, nullable, description, audit definitions)` of one parsed column.
pub(super) type ColumnSummary<'a> = (
    &'a str,
    Option<&'a str>,
    Option<bool>,
    Option<&'a str>,
    Vec<&'a str>,
);

pub(super) struct ModelFileStemTestCase {
    pub(super) description: &'static str,
    pub(super) relative_path: &'static str,
    pub(super) expected_stem: &'static str,
}
