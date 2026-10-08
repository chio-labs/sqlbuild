//! Python's `normalize_type`: Polyglot's parsed type first, then the text fallback.

use crate::type_system::_helpers::dialects::{coerce_type_dialect, polyglot_dialect};
use crate::type_system::_helpers::fallback::normalize_with_fallback;
use crate::type_system::_helpers::parsed::{normalize_parsed, parse_type};
use crate::type_system::constants::MAX_TYPE_BRACKETS;
use crate::type_system::models::{TypeDialect, TypeNormalization};

/// Normalize one type as Python does for the dialect name it hands Polyglot, or None to defer.
#[must_use]
pub fn normalize_type(type_sql: &str, dialect: &str) -> Option<TypeNormalization> {
    if !type_sql.is_ascii()
        || !dialect.is_ascii()
        || type_sql.bytes().filter(|byte| *byte == b'[').count() > MAX_TYPE_BRACKETS
    {
        return None;
    }
    let polyglot = polyglot_dialect(dialect)?;
    let type_dialect: Option<TypeDialect> = coerce_type_dialect(dialect);
    match parse_type(type_sql, &polyglot) {
        Ok(parsed) => Some(TypeNormalization {
            normalized: normalize_parsed(parsed, &polyglot, type_dialect)?,
            parse_error: None,
        }),
        Err(error) => Some(TypeNormalization {
            normalized: normalize_with_fallback(type_sql, type_dialect)?,
            parse_error: Some(error),
        }),
    }
}
