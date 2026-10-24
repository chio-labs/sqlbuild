use crate::compiled_project::models::SplicedSpan;
use crate::sql_macros::_helpers::typing::typed_calls::byte_splices;
use crate::sql_macros::models::TextSplice;

/// Character-offset `spans` from `source` to `output` as byte splices.
#[must_use]
pub fn byte_text_splices(source: &str, output: &str, spans: &[SplicedSpan]) -> Vec<TextSplice> {
    byte_splices(source, output, spans)
}
