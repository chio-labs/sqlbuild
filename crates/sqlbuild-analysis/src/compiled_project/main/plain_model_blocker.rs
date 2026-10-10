use crate::compiled_project::models::{PlainModelBlocker, PlainModelCheck};

/// Why the Python attachment must finish this model, or `None` when the native loop finishes it.
pub fn plain_model_blocker(check: &PlainModelCheck) -> Option<PlainModelBlocker> {
    crate::compiled_project::_helpers::plain::plain_model_blocker(check)
}
