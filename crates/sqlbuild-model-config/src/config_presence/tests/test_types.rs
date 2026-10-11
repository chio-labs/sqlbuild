use crate::tests::test_types::Value;

/// One authored config value and what each recursive scan finds in it.
pub(super) struct PresenceTestCase {
    pub(super) description: &'static str,
    pub(super) value: Value,
    pub(super) expected_template: bool,
    pub(super) expected_macro_call: bool,
}

/// One config value and whether it blocks reuse as metadata and is mutable when inherited.
pub(super) struct ReuseTestCase {
    pub(super) description: &'static str,
    pub(super) value: Value,
    pub(super) expected_blocks_reuse: bool,
    pub(super) expected_mutable: bool,
}
