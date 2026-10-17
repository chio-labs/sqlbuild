use std::sync::atomic::AtomicBool;

use crate::models::{RowsRequest, SpeculativeAnswer, SpeculativeRows};

/// Evaluate `request` as `evaluate_rows` would, from `speculative` only when its key matches.
pub fn answer_speculative_rows(
    speculative: SpeculativeRows,
    request: RowsRequest,
    stop: &AtomicBool,
) -> SpeculativeAnswer {
    crate::engine::_helpers::speculation::answer(speculative, request, stop)
}
