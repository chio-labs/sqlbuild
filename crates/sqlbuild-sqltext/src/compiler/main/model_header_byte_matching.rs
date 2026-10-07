use crate::compiler::_helpers::model_headers::matching::{self, HeaderMatchOffsets};

/// UTF-8 byte offsets of one matched header: header start, header end, and SQL start.
pub fn match_one_bytes(text: &str) -> Option<HeaderMatchOffsets> {
    matching::match_one_bytes(text)
}
