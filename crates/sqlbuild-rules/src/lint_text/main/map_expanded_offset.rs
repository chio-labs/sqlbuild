//! Map an offset of expanded SQL back to its authored text.

use crate::lint_text::_helpers::sql_diagnostics::map_offset;
use crate::lint_text::models::ExpansionSpan;

/// The authored offset of expanded character `offset`, and whether expansion generated it.
#[must_use]
pub fn map_expanded_offset(offset: i64, passes: &[Vec<ExpansionSpan>]) -> (i64, bool) {
    map_offset(offset, passes)
}
