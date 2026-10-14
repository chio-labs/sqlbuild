//! Resolve an offset in expanded SQL back onto the authored body.

use crate::compiled_project::_helpers::locating::map_through_passes;
use crate::compiled_project::models::SplicedSpan;

/// The offset in the first pass's source, and whether an expansion generated it.
#[must_use]
pub fn map_expanded_offset(offset: usize, passes: &[Vec<SplicedSpan>]) -> (usize, bool) {
    map_through_passes(offset, passes)
}
