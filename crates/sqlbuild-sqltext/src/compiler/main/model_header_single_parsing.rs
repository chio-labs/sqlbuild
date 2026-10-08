use crate::compiler::_helpers::model_headers::tokenization::{self, HeaderParseResult};

/// Parse one header on the calling thread; nesting is bounded, so any thread stack suffices.
pub fn parse_one(header: &str) -> HeaderParseResult {
    tokenization::parse_one(header)
}
