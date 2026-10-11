//! Why a declaration is rejected.

/// The exception a declaration failure raises.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum DeclarationFailure {
    /// `DeclarationParseError` with this message.
    Parse(String),
    /// `ResourceIdentityError` with its message and help.
    Identity(String, String),
    /// `decimal.Overflow` from normalizing a set of decimals.
    DecimalOverflow,
}
