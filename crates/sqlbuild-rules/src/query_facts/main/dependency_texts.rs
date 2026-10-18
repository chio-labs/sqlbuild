use crate::query_facts::models::ModelCall;

/// Every `__ref`/`__source` call in code, as the dependency text rules compare.
pub(crate) fn dependency_texts(calls: &[ModelCall]) -> Vec<String> {
    crate::query_facts::_helpers::shape::dependency_texts(calls)
}
