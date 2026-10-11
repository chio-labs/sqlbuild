//! Typed SQL value limits and the Python spellings their diagnostics use.

/// `decimal.DefaultContext.prec`, which `Decimal.normalize()` rounds to.
pub(crate) const DECIMAL_PRECISION: usize = 28;
/// `decimal.DefaultContext.Emax`.
pub(crate) const DECIMAL_EMAX: i64 = 999_999;
/// `decimal.DefaultContext.Emin`.
pub(crate) const DECIMAL_EMIN: i64 = -999_999;
/// Python's `MAX_EMAX`: larger exponents make `Decimal(text)` invalid.
pub(crate) const DECIMAL_MAX_EXPONENT: i64 = 999_999_999_999_999_999;
/// Plain notation is used down to this many places before the first digit.
pub(crate) const PLAIN_NOTATION_FLOOR: i64 = -6;
/// The scalar kinds, in `SqlValueKind` order.
pub(crate) const SCALAR_KINDS: [&str; 6] =
    ["string", "integer", "boolean", "float", "decimal", "null"];
pub(crate) const NULL_SIZE: i64 = 4;
pub(crate) const BOOLEAN_SIZE: i64 = 5;
/// Quotes or brackets around a string, key, or collection.
pub(crate) const DELIMITER_SIZE: i64 = 2;
pub(crate) const DECIMAL_KIND: &str = "decimal";
/// `0.0`, which also stands in for a normalized `-0.0`.
pub(crate) const POSITIVE_ZERO: f64 = 0.0;
