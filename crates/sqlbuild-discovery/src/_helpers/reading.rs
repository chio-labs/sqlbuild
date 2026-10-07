//! Read authored files as Python's `Path.read_text(encoding="utf-8")` does.

use crate::models::ReadFailure;
use sqlbuild_core::text::main::decode_python_text::decode_python_text;
use std::path::Path;

/// The decoded text, or why Python's read would raise.
pub(crate) fn read_authored_text(path: &Path) -> Result<String, ReadFailure> {
    let bytes: Vec<u8> = std::fs::read(path).map_err(|error| ReadFailure::Io(error.kind()))?;
    decode_python_text(&bytes).map_err(ReadFailure::Decode)
}
