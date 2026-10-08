use crate::compiler::models::NestingFailure;

pub(crate) struct ModelHeaderTokenizationTestCase {
    pub(crate) description: &'static str,
    pub(crate) run: fn() -> bool,
    pub(crate) expected_success: bool,
}

pub(crate) struct StaticSqlOperationTestCase {
    pub(crate) description: &'static str,
    pub(crate) run: fn() -> bool,
    pub(crate) expected_success: bool,
}

pub(crate) struct ModelHeaderMatchTestCase {
    pub(crate) description: &'static str,
    pub(crate) contents: &'static str,
    pub(crate) expected_offsets: Option<(usize, usize, usize)>,
}

pub(crate) struct DeclarationReferenceScanTestCase {
    pub(crate) description: &'static str,
    pub(crate) sql: &'static str,
    /// References spelled `kind:name[.member]@start..end, ...` in code points.
    pub(crate) expected_references: Option<&'static str>,
}

pub(crate) struct HeaderNestingTestCase {
    pub(crate) description: &'static str,
    /// The header is `prefix`, `open` repeated `depth` times, `1`, `close` as often, then `suffix`.
    pub(crate) prefix: &'static str,
    pub(crate) open: &'static str,
    pub(crate) close: &'static str,
    pub(crate) suffix: &'static str,
    pub(crate) depth: usize,
    /// The header position of the container past the limit; `None` when the header parses.
    pub(crate) expected_error_position: Option<usize>,
}

pub(crate) struct HeaderNestingLocationTestCase {
    pub(crate) description: &'static str,
    pub(crate) error: &'static str,
    pub(crate) header: &'static str,
    pub(crate) header_line: usize,
    pub(crate) expected_failure: Option<NestingFailure>,
}
