use crate::sql_macros::_helpers::typing::typed_calls::spliced;
use crate::sql_macros::models::{TextSplice, TypedCall};

/// `calls` moved by byte `splices`, sorted and non-overlapping; a call a splice cuts is dropped.
#[must_use]
pub fn moved_typed_calls(calls: Vec<TypedCall>, splices: &[TextSplice]) -> Vec<TypedCall> {
    spliced(calls, splices)
}
