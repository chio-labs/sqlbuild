use crate::query_facts::models::CallKind;

/// The call kind and occurrence a stubbed relation name stands for.
pub(crate) fn stub_call(name: &str) -> Option<(CallKind, usize)> {
    crate::query_facts::_helpers::shape::stub_call(name)
}
