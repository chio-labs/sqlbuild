/// An enum member's SQL literal: integers as written, text single-quoted with quotes doubled.
pub fn enum_member_literal(text: &str, integer: bool) -> String {
    crate::compiled_project::_helpers::splice::enum_member_literal(text, integer)
}
