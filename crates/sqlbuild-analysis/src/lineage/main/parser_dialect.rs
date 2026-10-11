//! The polyglot dialect Python's `dialect or "generic"` names, if Polyglot knows the name.

use polyglot_sql::DialectType;

/// Python's `parse_one(dialect=dialect or "generic")` dialect, or the name Polyglot does not know.
pub fn parser_dialect(name: Option<&str>) -> Result<DialectType, &str> {
    let name = name.filter(|name| !name.is_empty()).unwrap_or("generic");
    name.parse::<DialectType>().map_err(|_unknown_dialect| name)
}
