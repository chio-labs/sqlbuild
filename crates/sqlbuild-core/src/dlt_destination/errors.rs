//! dlt destination construction errors.

/// A destination the dlt integration cannot address, with its user-facing message.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DltDestinationError {
    pub message: String,
}
