use crate::path_defaults::models::PathDefaultChoice;

/// One model path, the configured keys, and the selection Python makes.
pub(super) struct SelectTestCase {
    pub(super) description: &'static str,
    pub(super) model_path: &'static str,
    pub(super) keys: &'static [&'static str],
    pub(super) expected_choice: PathDefaultChoice,
}
