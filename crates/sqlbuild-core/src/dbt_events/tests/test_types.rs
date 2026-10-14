use crate::dbt_events::models::{DbtEvent, DbtStreamUpdate};

pub(super) struct StreamTestCase {
    pub(super) description: &'static str,
    pub(super) events: Vec<DbtEvent>,
    pub(super) expected_updates: Vec<Option<DbtStreamUpdate>>,
}

pub(super) struct TextTestCase {
    pub(super) description: &'static str,
    pub(super) rendered: String,
    pub(super) expected_text: &'static str,
}
