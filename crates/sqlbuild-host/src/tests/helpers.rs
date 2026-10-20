use crate::types::ResultEnum;

/// Every member's Python value, in definition order.
pub(super) fn values<T: ResultEnum>() -> Vec<&'static str> {
    T::ALL.iter().map(|member| member.value()).collect()
}

/// Each member read back from its Python value, as that value.
pub(super) fn parsed<T: ResultEnum>() -> Vec<Option<&'static str>> {
    T::ALL
        .iter()
        .map(|member| T::from_value(member.value()).map(ResultEnum::value))
        .collect()
}
