use crate::models::SpeculativeRows;

/// Cancel a speculative evaluation and wait for its thread; nothing it held is written.
pub fn discard_speculative_rows(speculative: SpeculativeRows) {
    crate::engine::_helpers::speculation::discard(speculative);
}
