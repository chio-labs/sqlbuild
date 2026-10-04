pub(crate) fn evaluate_parts(
    request_json: &[u8],
    model_jsons: &[&[u8]],
    model_digests: &[String],
) -> Result<String, String> {
    crate::engine::_helpers::evaluation::evaluate_parts(request_json, model_jsons, model_digests)
}
