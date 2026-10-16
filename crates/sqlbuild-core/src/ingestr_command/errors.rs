//! Ingestr command construction errors.

/// A destination the ingestr integration cannot address, with its user-facing message.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct IngestrCommandError {
    pub message: String,
}
