pub(super) struct ApplyEditsTestCase {
    pub(super) description: &'static str,
    pub(super) text: &'static str,
    /// `(start, end, replacement)` in authoring order.
    pub(super) edits: &'static [(usize, usize, &'static str)],
    /// The edited text, or the overlap error message.
    pub(super) expected: Result<&'static str, &'static str>,
}

pub(super) struct IdentifierSitesTestCase {
    pub(super) description: &'static str,
    pub(super) text: &'static str,
    pub(super) names: &'static [&'static str],
    pub(super) expected_sites: &'static [(usize, usize, &'static str)],
}

pub(super) struct InterpolationSitesTestCase {
    pub(super) description: &'static str,
    pub(super) dialect: &'static str,
    pub(super) sql: &'static str,
    pub(super) expected_sites: &'static [&'static str],
}

pub(super) struct ResourceSitesTestCase {
    pub(super) description: &'static str,
    pub(super) sql: &'static str,
    /// `(kind, name, call text, name text)`.
    pub(super) expected_sites:
        &'static [(&'static str, &'static str, &'static str, &'static str)],
}

pub(super) struct AnalysisSqlTestCase {
    pub(super) description: &'static str,
    pub(super) sql: &'static str,
    pub(super) expected_sql: &'static str,
    /// `(kind, name, placeholders)`.
    pub(super) expected_tables: &'static [(&'static str, &'static str, &'static [&'static str])],
}

pub(super) struct HeaderEditsTestCase {
    pub(super) description: &'static str,
    pub(super) contents: &'static str,
    pub(super) expected_edits: &'static [&'static str],
    pub(super) expected_contents: &'static str,
}

pub(super) struct InsertEntryTestCase {
    pub(super) description: &'static str,
    pub(super) contents: &'static str,
    pub(super) expected_contents: Option<&'static str>,
}

pub(super) struct YamlEditsTestCase {
    pub(super) description: &'static str,
    pub(super) contents: &'static str,
    pub(super) expected_contents: &'static str,
}
