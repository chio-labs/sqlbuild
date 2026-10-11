//! Why a typed SQL value is rejected.

/// The exception normalizing a value raises.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum SqlValueFailure {
    /// `SqlValueValidationError` with this message.
    Invalid(String),
    /// `decimal.Overflow`, which `Decimal.normalize()` raises for an exponent past `Emax`.
    DecimalOverflow,
}
