use crate::sql_macros::_helpers::arguments::type_family;
use crate::sql_macros::models::{DeclaredOutput, TypeFamily};

/// The declared `returns` type an item takes over its inferred type: unknown or same family.
#[must_use]
pub fn sql_macro_declared_type(
    declared: &[DeclaredOutput],
    (cte, name): (Option<&str>, &str),
    inferred: Option<&str>,
    dialect: &str,
) -> Option<String> {
    let output: &DeclaredOutput = declared.iter().find(|output| {
        output.name.eq_ignore_ascii_case(name)
            && match (&output.cte, cte) {
                (None, None) => true,
                (Some(declared_cte), Some(cte)) => declared_cte.eq_ignore_ascii_case(cte),
                _ => false,
            }
    })?;
    let Some(inferred) = inferred.filter(|inferred| !inferred.is_empty()) else {
        return Some(output.returns.clone());
    };
    let inferred_family: TypeFamily = type_family(inferred, dialect);
    let refines: bool = inferred_family == TypeFamily::Unknown
        || inferred_family == type_family(&output.returns, dialect);
    refines.then(|| output.returns.clone())
}
