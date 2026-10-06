use sqlparser::dialect::Dialect;

/// Return the parser dialect rules use for `name`, falling back to the generic dialect.
pub fn rules_dialect(name: &str) -> Box<dyn Dialect> {
    crate::sql_scan::_helpers::rules_dialect::rules_dialect(name)
}
