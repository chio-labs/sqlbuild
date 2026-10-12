//! The canonical order of scope diagnostics.

use crate::placement::models::DiagnosticOrderKey;

/// Positions of `keys` in Python's stable sort by path, line, column, code and message.
#[must_use]
pub fn diagnostic_order(keys: &[DiagnosticOrderKey]) -> Vec<usize> {
    let mut positions: Vec<usize> = (0..keys.len()).collect();
    positions.sort_by_key(|position| {
        let key: &DiagnosticOrderKey = &keys[*position];
        (
            key.path.as_deref().unwrap_or_default(),
            key.line.unwrap_or_default(),
            key.column.unwrap_or_default(),
            key.code.as_str(),
            key.message.as_str(),
        )
    });
    positions
}
