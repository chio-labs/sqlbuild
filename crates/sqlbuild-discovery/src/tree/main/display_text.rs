//! Path text as users see it, with names that are not valid UTF-8 shown lossily.

use crate::tree::_helpers::raw_names;
use std::borrow::Cow;

/// `text` with each raw path segment replaced by its lossy name.
pub fn display_text(text: &str) -> Cow<'_, str> {
    raw_names::display_text(text)
}
