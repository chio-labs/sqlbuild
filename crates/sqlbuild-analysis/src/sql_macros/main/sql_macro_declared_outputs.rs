use crate::sql_macros::models::{CallScope, DeclaredOutput, SqlMacroCheck};

/// The select items, in any set-operation branch, of a model's top-level queries that are one call.
#[must_use]
pub fn sql_macro_declared_outputs(checks: &[SqlMacroCheck]) -> Vec<DeclaredOutput> {
    checks
        .iter()
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
                branch: output.branch,
            })
        })
        .collect()
}
