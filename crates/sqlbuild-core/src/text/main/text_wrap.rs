//! Python's `textwrap.wrap`.

use crate::text::_helpers::text_wrap::wrap;

/// `textwrap.wrap(text, width, initial_indent=initial, subsequent_indent=subsequent, break_on_hyphens=...)`.
#[must_use]
pub fn text_wrap(
    text: &str,
    width: usize,
    indents: (&str, &str),
    break_on_hyphens: bool,
) -> Vec<String> {
    wrap(text, width, indents, break_on_hyphens)
}
