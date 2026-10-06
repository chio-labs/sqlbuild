/// Return whether SQL lint treats backticks as identifier quotes for `dialect`.
pub(crate) fn backtick_identifiers(dialect: &str) -> bool {
    crate::sql_lint::_helpers::preparation::backtick_identifiers(dialect)
}
