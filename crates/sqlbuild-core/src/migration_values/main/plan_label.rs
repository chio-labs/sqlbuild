//! The plan label of a model migration decision or promotion.

/// `value` with underscores shown as spaces.
#[must_use]
pub fn plan_label(value: &str) -> String {
    value.replace('_', " ")
}
