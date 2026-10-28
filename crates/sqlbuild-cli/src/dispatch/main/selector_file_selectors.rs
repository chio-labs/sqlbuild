//! The selectors a `--select-file` lists.

use sqlbuild_core::text::main::python_splitlines::python_splitlines;
use sqlbuild_core::text::main::python_strip::python_strip;

use crate::dispatch::constants::SELECTOR_COMMENT_PREFIX;

/// One selector per stripped line of `text`, without blank lines and `#` comments.
#[must_use]
pub fn selector_file_selectors(text: &str) -> Vec<String> {
    python_splitlines(text)
        .into_iter()
        .map(python_strip)
        .filter(|line| !line.is_empty() && !line.starts_with(SELECTOR_COMMENT_PREFIX))
        .map(str::to_owned)
        .collect()
}
