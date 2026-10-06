pub(crate) fn run_custom_host_json(spec_json: &str) -> Result<String, String> {
    crate::engine::_helpers::custom_host::run_custom_host_json(spec_json)
}
