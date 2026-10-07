use crate::compiler::_helpers::model_headers::matching::{self, HeaderMatchOffsets};

/// Byte offsets (header start, header end, match end) of `\s*KEYWORD\s*\(header\)\s*;\s*`.
pub fn match_statement_header(
    text: &str,
    start: usize,
    keyword: &str,
) -> Option<HeaderMatchOffsets> {
    matching::match_statement_bytes(text, start, keyword.as_bytes())
}
