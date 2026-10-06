use crate::compiler::_helpers::model_headers::tokenization::{self, HeaderParseResult};

pub(crate) fn parse_batch(headers: &[String]) -> Result<Vec<HeaderParseResult>, String> {
    tokenization::parse_batch(headers)
}
