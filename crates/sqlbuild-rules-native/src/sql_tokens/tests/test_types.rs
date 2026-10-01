pub(crate) struct CanonicalTokensTestCase {
    pub(crate) description: &'static str,
    pub(crate) dialect: polyglot_sql::DialectType,
    pub(crate) left: &'static str,
    pub(crate) right: &'static str,
    pub(crate) expected_equal: bool,
}
