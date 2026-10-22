use crate::definition_changes::models::{DefinitionSnapshot, ExecutedItem};

pub(crate) struct SelectionReasonTestCase {
    pub(crate) description: &'static str,
    pub(crate) current: DefinitionSnapshot,
    pub(crate) item: ExecutedItem,
    pub(crate) expected_reasons: &'static [&'static str],
}
