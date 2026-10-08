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
