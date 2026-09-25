/// Return the quoting policy rules use when scanning SQL for `dialect_name`.
pub(crate) fn quote_policy(dialect_name: &str) -> crate::sql_scan::models::QuotePolicy {
    crate::rules::_helpers::evaluation::rules_quote_policy(dialect_name)
}
