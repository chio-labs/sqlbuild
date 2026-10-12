//! Conversions between Python code point offsets and UTF-8 byte offsets.

use crate::code_scanner::models::CodeScanner;

/// The byte offset of the code point at `index`, or the text length past the end.
pub(crate) fn byte_offset(scanner: &CodeScanner, index: usize) -> usize {
    if scanner.char_bytes.is_empty() {
        return index.min(scanner.sql.len());
    }
    scanner
        .char_bytes
        .get(index)
        .copied()
        .unwrap_or(scanner.sql.len())
}

/// The code point offset of a byte offset at a code point boundary.
pub(crate) fn char_offset(scanner: &CodeScanner, byte: usize) -> usize {
    if scanner.char_bytes.is_empty() {
        return byte;
    }
    scanner.char_bytes.partition_point(|start| *start < byte)
}
