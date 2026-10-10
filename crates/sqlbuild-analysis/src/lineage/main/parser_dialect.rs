//! The polyglot dialect Python's `dialect or "generic"` names, if Polyglot knows the name.

use polyglot_sql::DialectType;

/// Python's `parse_one(dialect=dialect or "generic")` dialect, if Polyglot knows the name.
pub fn parser_dialect(name: Option<&str>) -> Option<DialectType> {
    let name = name.filter(|name| !name.is_empty()).unwrap_or("generic");
    name.parse::<DialectType>().ok()
}
