/// Return the quoting policy rules use when scanning SQL for `dialect_name`.
pub fn quote_policy(dialect_name: &str) -> crate::sql_scan::models::QuotePolicy {
    crate::sql_scan::_helpers::rules_dialect::rules_quote_policy(dialect_name)
}
