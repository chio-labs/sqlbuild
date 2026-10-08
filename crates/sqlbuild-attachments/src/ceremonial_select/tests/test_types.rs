use crate::ceremonial_select::models::OmittedSelect;

pub(super) struct OmittedSelectTestCase {
    pub(super) description: &'static str,
    pub(super) sql: &'static str,
    pub(super) expected_offset: OmittedSelect,
}
