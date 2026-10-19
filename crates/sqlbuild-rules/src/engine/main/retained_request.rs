use crate::models::{EvaluateRequest, RetainedRows};

/// The request a compile retained, its models without SQL text; `None` when it is damaged.
pub fn retained_request(retained: &RetainedRows) -> Option<EvaluateRequest> {
    let Ok(request) = crate::engine::_helpers::retained::retained_request(retained) else {
        return None;
    };
    Some(request)
}
