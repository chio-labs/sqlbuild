use crate::models::EvaluateRequest;

pub(crate) fn parse_parts(
    request_json: &[u8],
    model_jsons: &[&[u8]],
    model_digests: &[String],
) -> Result<EvaluateRequest, String> {
    crate::engine::_helpers::evaluation::parse_parts(request_json, model_jsons, model_digests)
}
