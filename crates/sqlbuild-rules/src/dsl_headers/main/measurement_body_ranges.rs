//! `measurement_body_ranges`: the query bodies of MEASURE and EVIDENCE blocks.

use crate::dsl_headers::_helpers::scan::{delimited_regions, first_non_whitespace};
use crate::dsl_headers::_helpers::text::rfind_before;
use crate::dsl_headers::constants::MEASUREMENT_KINDS;

/// The authored query ranges inside MEASURE and EVIDENCE blocks.
pub fn measurement_body_ranges(text: &[char]) -> Vec<(usize, usize)> {
    let mut ranges: Vec<(usize, usize)> = Vec::new();
    for block in delimited_regions(text, &MEASUREMENT_KINDS, false) {
        let opening: usize = (block.start..block.end)
            .find(|index| text[*index] == '(')
            .unwrap_or(block.start);
        let after_opening: usize = opening + 1;
        let closing: usize = rfind_before(text, ')', block.end)
            .filter(|found| *found >= after_opening)
            .unwrap_or(after_opening);
        let body_start: usize = first_non_whitespace(text, after_opening, closing);
        if body_start < closing {
            ranges.push((body_start, closing));
        }
    }
    ranges
}
