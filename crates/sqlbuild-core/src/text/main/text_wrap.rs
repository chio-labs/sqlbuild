//! Python's `textwrap.wrap` with its default options.

use crate::text::_helpers::text_wrap::wrap;

/// `textwrap.wrap(text, width, initial_indent=initial, subsequent_indent=subsequent)`.
#[must_use]
pub fn text_wrap(text: &str, width: usize, indents: (&str, &str)) -> Vec<String> {
    wrap(text, width, indents)
}
