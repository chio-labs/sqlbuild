pub(crate) struct MatchTestCase {
    pub(crate) description: &'static str,
    /// `(name, schema, database)` written in SQL.
    pub(crate) written: (&'static str, Option<&'static str>, Option<&'static str>),
    /// The matched `(kind, name, compatibility_for)`, or None.
    pub(crate) expected_match: Option<(&'static str, &'static str, Option<&'static str>)>,
}
