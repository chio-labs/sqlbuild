use crate::compiler::_helpers::model_headers::matching::{self, HeaderMatchOffsets};

pub(crate) fn match_batch(contents: &[String]) -> Vec<Option<HeaderMatchOffsets>> {
    contents
        .iter()
        .map(|text| matching::match_one(text))
        .collect()
}
