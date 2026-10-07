use crate::templates::models::{StringExpansion, TemplateFailure};
use crate::templates::tests::test_types::Value;

/// A substituted string.
pub(super) fn text(value: &str) -> Result<StringExpansion<Value>, TemplateFailure> {
    Ok(StringExpansion::Text(value.to_owned()))
}

/// A whole-string template's value.
pub(super) fn value(value: Value) -> Result<StringExpansion<Value>, TemplateFailure> {
    Ok(StringExpansion::Value(value))
}
