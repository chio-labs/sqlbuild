//! Why Python rejects a function header's named type map.

/// Which check of a named type map fails first.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) enum NamedTypeError {
    InvalidName,
    /// The authored name of the entry without a type.
    MissingType(String),
}
