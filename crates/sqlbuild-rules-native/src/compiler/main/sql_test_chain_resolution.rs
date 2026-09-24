use crate::compiler::_helpers;

pub(crate) fn resolve_chains_json(request_json: &str) -> Result<String, String> {
    _helpers::sql_tests::planning::resolve_chains_json(request_json)
}
