//! Errors raised while reading expressions for fast lineage.

use std::fmt::{self, Display};

use serde::ser;

/// An expression pythonize could not have serialized.
#[derive(Debug)]
pub(crate) struct PayloadError(String);

impl PayloadError {
    pub(crate) fn new(message: &str) -> Self {
        Self(message.to_owned())
    }
}

impl Display for PayloadError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.0)
    }
}

impl std::error::Error for PayloadError {}

impl ser::Error for PayloadError {
    fn custom<T: Display>(message: T) -> Self {
        Self(message.to_string())
    }
}
