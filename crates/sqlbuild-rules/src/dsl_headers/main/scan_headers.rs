//! `scan_headers`: every DSL header span of a file.

use crate::dsl_headers::_helpers::scan::delimited_regions;
use crate::dsl_headers::constants::HEADER_KINDS;
use crate::dsl_headers::models::HeaderSpan;

/// Every DSL header span in `text`, or only the first.
pub fn scan_headers(text: &[char], first_only: bool) -> Vec<HeaderSpan> {
    delimited_regions(text, &HEADER_KINDS, first_only)
}
