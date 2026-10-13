//! Cursor errors built from fixed messages.

use crate::algebra::errors::CursorError;

pub(crate) fn algebra(message: &str) -> CursorError {
    CursorError::Algebra(message.to_owned())
}

pub(crate) fn overflow(message: &str) -> CursorError {
    CursorError::Overflow(message.to_owned())
}
