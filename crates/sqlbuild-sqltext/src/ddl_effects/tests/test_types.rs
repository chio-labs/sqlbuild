pub(super) struct StatementEffectTestCase {
    pub(super) description: &'static str,
    pub(super) sql: &'static str,
    pub(super) expected_relation_names: &'static [&'static str],
    pub(super) expected_invalidates_all: bool,
    pub(super) expected_ends_transaction: bool,
}

pub(super) struct NameKeyTestCase {
    pub(super) description: &'static str,
    pub(super) name: &'static str,
    pub(super) expected_key: Option<&'static str>,
}
