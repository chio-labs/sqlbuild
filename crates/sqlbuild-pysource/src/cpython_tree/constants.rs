//! Constants of CPython's parse of a source text.

/// The byte order mark CPython rejects as a non-printable character at the start of a `str` source.
pub(crate) const BYTE_ORDER_MARK: char = '\u{feff}';
