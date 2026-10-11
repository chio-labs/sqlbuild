/// Whether declaration-expanded SQL still calls macros, which the attachment expands.
pub fn calls_macros(sql: &str) -> bool {
    crate::compiled_project::_helpers::plain::calls_macros(sql)
}
