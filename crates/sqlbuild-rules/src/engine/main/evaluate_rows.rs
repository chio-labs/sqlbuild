use crate::errors::RowsError;
use crate::models::{RowsEvaluation, RowsRequest};

/// Answer a built request from the response memo or evaluate it, remembering the response.
pub fn evaluate_rows(request: RowsRequest) -> Result<RowsEvaluation, RowsError> {
    crate::engine::_helpers::memo::evaluate_rows(request)
}
