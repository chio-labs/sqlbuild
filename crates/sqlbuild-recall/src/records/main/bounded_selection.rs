//! `bounded_selection`: the selectors a context row records, within its bound.

use crate::records::constants::MAX_RECORDED_SELECTION_BYTES;

/// The leading selectors whose text fits [`MAX_RECORDED_SELECTION_BYTES`], and whether any were left out.
#[must_use]
pub fn bounded_selection(selectors: Vec<String>) -> (Vec<String>, bool) {
    let mut used: usize = 0;
    let mut kept: Vec<String> = Vec::with_capacity(selectors.len());
    let total: usize = selectors.len();
    for selector in selectors {
        used += selector.len();
        if used > MAX_RECORDED_SELECTION_BYTES {
            break;
        }
        kept.push(selector);
    }
    let truncated: bool = kept.len() < total;
    (kept, truncated)
}
