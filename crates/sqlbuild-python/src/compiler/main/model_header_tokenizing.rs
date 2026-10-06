use crate::compiler::_helpers::model_headers::tokenization::{self, HeaderToken};

pub(crate) fn tokenize_one(header: &str) -> Result<Vec<HeaderToken>, String> {
    tokenization::tokenize_one(header)
}
