//! ASCII text operations that match Python's `str` methods; other text is left to Python.

use crate::model_validation::constants::SETTING_SNIPPET_INDENT;
use crate::model_validation::models::Rejected;

/// Return Python's `text.strip()` for ASCII text, or reject other text.
pub(crate) fn python_strip(text: &str) -> Result<&str, Rejected> {
    if text.is_ascii() {
        Ok(text.trim_matches(|character: char| is_python_space(character as u8)))
    } else {
        Err(Rejected)
    }
}

/// Return Python's `text.lower()` for ASCII text, or reject other text.
pub(crate) fn python_lower(text: &str) -> Result<String, Rejected> {
    if text.is_ascii() {
        Ok(text.to_ascii_lowercase())
    } else {
        Err(Rejected)
    }
}

fn is_python_space(byte: u8) -> bool {
    matches!(byte, b'\t'..=b'\r' | 0x1c..=0x1f | b' ')
}

/// Return `model_header_help`: the purpose, then the exact MODEL header entry to add.
pub(crate) fn model_header_help(purpose: &str, entry: &str) -> String {
    let indent = SETTING_SNIPPET_INDENT;
    format!(
        "{purpose}, add this to the MODEL header:\n{indent}MODEL (\n{indent}  {entry},\n\
         {indent}  ...\n{indent});"
    )
}
