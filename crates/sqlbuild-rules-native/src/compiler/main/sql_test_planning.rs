use crate::compiler::_helpers;

pub(crate) fn plan_and_render_json(request_json: &str) -> Result<String, String> {
    _helpers::sql_tests::planning::plan_and_render_json(request_json)
}
