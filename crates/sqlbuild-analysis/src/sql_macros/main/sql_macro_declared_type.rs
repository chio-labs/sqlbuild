use crate::sql_macros::models::DeclaredOutput;
use crate::type_system::main::normalize_type::normalize_type;
use crate::type_system::models::TypeFamily;

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
    let Some(inferred_family) = known_family(inferred, dialect) else {
        return Some(output.returns.clone());
    };
    (known_family(&output.returns, dialect) == Some(inferred_family))
        .then(|| output.returns.clone())
}

/// The family of `data_type`, `Other` included; `None` where it does not normalise.
fn known_family(data_type: &str, dialect: &str) -> Option<TypeFamily> {
    normalize_type(data_type, dialect)
        .ok()
        .map(|normalization| normalization.normalized.family)
}
