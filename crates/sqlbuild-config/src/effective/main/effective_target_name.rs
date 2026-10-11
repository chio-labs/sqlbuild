//! `resolve_target_name`: the selected, local, then project default target.

use crate::effective::errors::EffectiveConfigError;
use crate::effective::models::TargetChoice;

/// The effective target name, `None` when nothing selects one, or why the name is unknown.
pub fn effective_target_name<K: Eq + Clone>(
    choice: TargetChoice<K>,
) -> Result<Option<K>, EffectiveConfigError<K>> {
    let Some(name) = choice.selected.or(choice.local).or(choice.default) else {
        return Ok(None);
    };
    if choice.defined.contains(&name) {
        Ok(Some(name))
    } else {
        Err(EffectiveConfigError::UnknownTarget(name))
    }
}
