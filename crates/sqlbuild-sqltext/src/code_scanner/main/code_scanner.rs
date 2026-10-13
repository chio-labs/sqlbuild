//! Prepare one SQL text for scanning at Python string offsets.

use crate::code_scanner::models::CodeScanner;
use crate::sql_scan::models::LexicalSyntax;

/// A scanner over `sql`, under `syntax` when given and the generic compiler rules otherwise.
#[must_use]
pub fn code_scanner(sql: &str, syntax: Option<LexicalSyntax>) -> CodeScanner {
    let char_bytes: Vec<usize> = if sql.is_ascii() {
        Vec::new()
    } else {
        sql.char_indices()
            .map(|(offset, _)| offset)
            .chain([sql.len()])
            .collect()
    };
    CodeScanner {
        sql: sql.to_owned(),
        char_bytes,
        syntax,
    }
}
