//! The profile output a run connects with.

use crate::dbt_profile::errors::DbtProfileError;
use crate::dbt_profile::models::DbtProfileOutputs;

/// The requested target, else the profile default, with the entry index of its output.
pub fn select_dbt_profile_target(
    profile: &DbtProfileOutputs,
    requested: Option<&str>,
) -> Result<(String, usize), DbtProfileError> {
    let selected: &str = match requested.filter(|target| !target.is_empty()) {
        Some(target) => target,
        None => profile.default_target.as_deref().ok_or_else(|| {
            DbtProfileError(format!(
                "dbt profile '{}' does not define a default target; pass --target",
                profile.name
            ))
        })?,
    };
    match profile.outputs.iter().find(|(name, _)| name == selected) {
        Some((name, index)) => Ok((name.clone(), *index)),
        None => {
            let mut available: Vec<&str> = profile
                .outputs
                .iter()
                .map(|(name, _)| name.as_str())
                .collect();
            available.sort_unstable();
            Err(DbtProfileError(format!(
                "dbt profile '{}' does not define target '{selected}'. Available targets: {}",
                profile.name,
                available.join(", ")
            )))
        }
    }
}
