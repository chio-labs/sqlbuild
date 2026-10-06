use crate::models::EvaluateRequest;

pub(crate) fn evaluate_parsed(request: EvaluateRequest) -> Result<String, String> {
    crate::engine::_helpers::evaluation::evaluate_request(request)
}
