//! Python's `normalize_type`: Polyglot's parsed type first, then the text fallback.

use polyglot_sql::{Dialect, DialectType};

use crate::type_system::_helpers::dialects::coerce_type_dialect;
use crate::type_system::_helpers::fallback::normalize_with_fallback;
use crate::type_system::_helpers::parsed::{normalize_parsed, parse_type};
use crate::type_system::models::{TypeDialect, TypeNormalization, TypeNormalizationError};

/// Normalize one type as Python does for the dialect name it hands Polyglot.
///
/// # Errors
///
/// Python's exception where it raises: an unknown dialect or an unwritable parsed type.
pub fn normalize_type(
    type_sql: &str,
    dialect: &str,
) -> Result<TypeNormalization, TypeNormalizationError> {
    let name: &str = if dialect.is_empty() {
        "generic"
    } else {
        dialect
    };
    let polyglot: Dialect = name
        .parse::<DialectType>()
        .map(Dialect::get)
        .map_err(|_| TypeNormalizationError::UnknownDialect(name.to_owned()))?;
    let type_dialect: Option<TypeDialect> = coerce_type_dialect(dialect);
    match parse_type(type_sql, &polyglot) {
        Ok(parsed) => Ok(TypeNormalization {
            normalized: normalize_parsed(parsed, &polyglot, type_dialect)?,
            parse_error: None,
        }),
        Err(error) => Ok(TypeNormalization {
            normalized: normalize_with_fallback(type_sql, type_dialect),
            parse_error: Some(error),
        }),
    }
}
