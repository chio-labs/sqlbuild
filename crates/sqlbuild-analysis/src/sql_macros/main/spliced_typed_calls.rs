use crate::compiled_project::models::SplicedSpan;
use crate::sql_macros::_helpers::typing::typed_calls::{byte_splices, spliced};
use crate::sql_macros::models::{TextSplice, TypedCall};

/// `calls` in `source` moved to `output` by character-offset `spans`; a call a span cuts is dropped.
#[must_use]
pub fn spliced_typed_calls(
    calls: Vec<TypedCall>,
    (source, output): (&str, &str),
    spans: &[SplicedSpan],
) -> Vec<TypedCall> {
    if calls.is_empty() {
        return calls;
    }
    let splices: Vec<TextSplice> = byte_splices(source, output, spans);
    spliced(calls, &splices)
}
