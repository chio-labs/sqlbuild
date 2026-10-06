use crate::compiler::_helpers;

pub fn render_difference_sample_json(request_json: &str) -> Result<String, String> {
    _helpers::sql_tests::rendering::render_difference_sample_json(request_json)
}
