pub(crate) struct ReferenceTestCase {
    pub(crate) description: &'static str,
    pub(crate) sql: &'static str,
    pub(crate) expected_resources: &'static [(&'static str, &'static str, &'static str)],
    pub(crate) expected_normalized: &'static str,
}

pub(crate) struct ParsedLineageTestCase {
    pub(crate) description: &'static str,
    pub(crate) dialect: Option<&'static str>,
    pub(crate) sql: &'static str,
    pub(crate) inferred_columns: &'static [&'static str],
    pub(crate) expected_status: &'static str,
    /// One `output transform confidence [type:resource.column ...]` line per column.
    pub(crate) expected_lines: &'static [&'static str],
    pub(crate) expected_has_star: bool,
    pub(crate) expected_detail: Option<&'static str>,
}

pub(crate) struct StarExpansionTestCase {
    pub(crate) description: &'static str,
    pub(crate) sql: &'static str,
    pub(crate) existing_columns: &'static [&'static str],
    pub(crate) expected_lines: &'static [&'static str],
}
