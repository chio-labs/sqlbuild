use std::borrow::Cow;

use crate::sql_macros::_helpers::typing::typed_calls::without_marker_calls;

/// `text` with each analysis-only typed marker call replaced by the expression it typed.
#[must_use]
pub fn marker_free_text(text: &str) -> Cow<'_, str> {
    without_marker_calls(text)
}
