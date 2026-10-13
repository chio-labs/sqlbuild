//! The P008 message for SQL naming a relation kept only as a compatibility view.

/// `old_name_reference_message`: `owner_label` wrote `written` in SQL passed to `ctx.<method>()`.
#[must_use]
pub fn old_name_message(
    owner_label: &str,
    written: &str,
    method: &str,
    model_name: &str,
) -> String {
    format!(
        "{owner_label} names '{written}' in SQL passed to ctx.{method}(); it is the old name of \
         model:{model_name}, kept only as a compatibility view for consumers outside the project"
    )
}
