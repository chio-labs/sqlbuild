/// Python's `selector_name_help`: the "did you mean" text for an unknown name, if any.
pub fn selector_name_help(value: &str, candidates: Vec<&str>) -> Option<String> {
    if crate::graph::_helpers::selectors::is_pattern(value) {
        return None;
    }
    crate::graph::_helpers::selectors::suggestion(value, candidates)
}
