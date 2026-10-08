//! Which construct Python reports unclosed where its comment and quote scan raises.

use sqlbuild_sqltext::sql_scan::models::Unclosed;

/// A block comment when `index` opens one, otherwise quoted text.
#[must_use]
pub fn unclosed_construct(bytes: &[u8], index: usize) -> Unclosed {
    if bytes[index..].starts_with(b"/*") {
        Unclosed::BlockComment
    } else {
        Unclosed::Quote
    }
}
