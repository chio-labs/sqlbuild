use crate::constants::UNKNOWN_SQL_TYPE;
use crate::sql_macros::models::DeclaredOutput;
use crate::type_system::main::normalize_type::normalize_type;
use crate::type_system::models::NormalizedType;

/// The declared `returns` type an item takes over its inferred type: unknown or identical.
#[must_use]
pub fn sql_macro_declared_type(
    declared: &[DeclaredOutput],
    (cte, branch, name): (Option<&str>, usize, &str),
    inferred: Option<&str>,
    dialect: &str,
) -> Option<String> {
    let output: &DeclaredOutput = declared.iter().find(|output| {
        output.name.eq_ignore_ascii_case(name)
            && output.branch == branch
            && match (&output.cte, cte) {
                (None, None) => true,
                (Some(declared_cte), Some(cte)) => declared_cte.eq_ignore_ascii_case(cte),
                _ => false,
            }
    })?;
    let Some(inferred) = inferred.filter(|inferred| {
        !inferred.is_empty() && !inferred.eq_ignore_ascii_case(UNKNOWN_SQL_TYPE)
    }) else {
        return Some(output.returns.clone());
    };
    let Some(inferred_type) = normalized(inferred, dialect) else {
        return Some(output.returns.clone());
    };
    (normalized(&output.returns, dialect) == Some(inferred_type)).then(|| output.returns.clone())
}

/// `data_type` as compared, or `None` where it does not normalise.
fn normalized(data_type: &str, dialect: &str) -> Option<NormalizedType> {
    match normalize_type(data_type, dialect) {
        Ok(normalization) => Some(normalization.normalized),
        Err(_unnormalizable) => None,
    }
}
