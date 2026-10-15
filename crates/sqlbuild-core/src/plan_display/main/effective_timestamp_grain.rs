//! The coarsest timestamp grain participating in cursor replay.

use crate::plan_display::constants::{
    DEFAULT_CURSOR_GRAIN, GRAIN_BATCH_SIZE, TIMESTAMP_CURSOR, WATERMARK_STRATEGY,
};
use crate::plan_display::errors::UnknownCursorGrain;
use crate::plan_display::models::TimestampGrainFacts;

/// The grain's position from finest to coarsest; an unknown grain is an error.
fn grain_rank(grain: &str) -> Result<usize, UnknownCursorGrain> {
    GRAIN_BATCH_SIZE
        .iter()
        .position(|(known, _)| *known == grain)
        .ok_or_else(|| UnknownCursorGrain(grain.to_owned()))
}

/// The declared grain or `second`, an empty grain counting as absent.
fn grain_or_default(grain: Option<&String>) -> String {
    grain
        .filter(|grain| !grain.is_empty())
        .map_or_else(|| DEFAULT_CURSOR_GRAIN.to_owned(), Clone::clone)
}

/// `None` for non-timestamp cursors; the declared grain for watermark replay; else the coarsest declared or input grain.
pub fn effective_timestamp_grain(
    facts: &TimestampGrainFacts,
) -> Result<Option<String>, UnknownCursorGrain> {
    if facts.cursor_type.as_deref() != Some(TIMESTAMP_CURSOR) {
        return Ok(None);
    }
    let mut effective: String = grain_or_default(facts.downstream_grain.as_ref());
    if facts.microbatch_strategy.as_deref() == Some(WATERMARK_STRATEGY) {
        return Ok(Some(effective));
    }
    for input_grain in &facts.input_grains {
        let candidate: String = grain_or_default(input_grain.as_ref());
        if grain_rank(&candidate)? > grain_rank(&effective)? {
            effective = candidate;
        }
    }
    Ok(Some(effective))
}
