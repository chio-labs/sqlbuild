use crate::compiler::_helpers::model_headers::tokenization::{self, HeaderParseResult};

/// Parse one header on the calling thread; deep headers need a large worker stack.
pub fn parse_one(header: &str) -> HeaderParseResult {
    tokenization::parse_one(header)
}
