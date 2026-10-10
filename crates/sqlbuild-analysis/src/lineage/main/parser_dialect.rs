//! The polyglot dialect Python's `dialect or "generic"` names, if this parser build carries it.

use polyglot_sql::DialectType;

use crate::lineage::_helpers::dialects::is_compiled_dialect;

/// Python's `parse_one(dialect=dialect or "generic")` dialect, if this parser build carries it.
pub fn parser_dialect(name: Option<&str>) -> Option<DialectType> {
    let name = name.filter(|name| !name.is_empty()).unwrap_or("generic");
    let Ok(dialect) = name.parse::<DialectType>() else {
        return None;
    };
    is_compiled_dialect(dialect).then_some(dialect)
}
