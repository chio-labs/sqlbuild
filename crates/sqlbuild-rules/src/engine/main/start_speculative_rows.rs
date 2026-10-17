use crate::models::{RowsRequest, SpeculativeRows};

/// Evaluate a built request on its own thread, holding every cache and memo write it would make.
pub fn start_speculative_rows(request: RowsRequest) -> std::io::Result<SpeculativeRows> {
    crate::engine::_helpers::speculation::start(request)
}
