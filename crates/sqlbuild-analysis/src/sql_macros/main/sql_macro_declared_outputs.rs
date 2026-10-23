use crate::sql_macros::models::{CallScope, DeclaredOutput, SqlMacroCheck};

/// The select items of a model's main query and top-level CTEs that are one macro call each.
#[must_use]
pub fn sql_macro_declared_outputs(checks: &[SqlMacroCheck]) -> Vec<DeclaredOutput> {
    checks
        .iter()
        .filter(|check| check.plain_select)
        .filter_map(|check| {
            let output = check.output.as_ref()?;
            let cte: Option<String> = match &check.scope {
                CallScope::Main => None,
                CallScope::Cte(name) => Some(name.clone()),
                CallScope::WithList => return None,
            };
            Some(DeclaredOutput {
                cte,
                name: output.name.clone(),
                returns: output.returns.clone(),
            })
        })
        .collect()
}
