pub(crate) struct ColumnReferenceTestCase {
    pub(crate) description: &'static str,
    pub(crate) sql: &'static str,
    pub(crate) output_ctes: &'static [&'static str],
    pub(crate) expected_parsed: bool,
    pub(crate) expected_names: &'static [&'static str],
    pub(crate) expected_scopes: &'static [&'static str],
    pub(crate) expected_bare_projections: usize,
    pub(crate) expected_aliases: &'static [&'static str],
    pub(crate) expected_star_scopes: &'static [&'static str],
    pub(crate) expected_joins: usize,
    pub(crate) expected_output_aliases: &'static [&'static str],
    pub(crate) expected_outputs: usize,
}
