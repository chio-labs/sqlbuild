//! The microbatch size after cursor-grain propagation.

use crate::plan_display::constants::{EFFECTIVE_BATCH_SIZE_TOKEN, GRAIN_BATCH_SIZE};
use crate::plan_display::errors::UnknownCursorGrain;

/// The declared size, or the grain's single-unit size for the `effective` token; an unknown grain is an error.
pub fn effective_microbatch_batch_size(
    batch_size: &str,
    effective_grain: &str,
) -> Result<String, UnknownCursorGrain> {
    if batch_size != EFFECTIVE_BATCH_SIZE_TOKEN {
        return Ok(batch_size.to_owned());
    }
    GRAIN_BATCH_SIZE
        .iter()
        .find(|(grain, _)| *grain == effective_grain)
        .map(|(_, size)| (*size).to_owned())
        .ok_or_else(|| UnknownCursorGrain(effective_grain.to_owned()))
}
