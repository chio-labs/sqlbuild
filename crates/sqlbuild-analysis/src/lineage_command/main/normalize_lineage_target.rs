//! A lineage target without its printed kind prefix.

use crate::lineage_command::_helpers::targets::unknown_lineage_target;
use crate::lineage_command::errors::LineageError;
use crate::lineage_command::main::resolve_lineage_target::resolve_lineage_target;
use crate::lineage_command::models::{LineageKey, LineageTarget};

/// Strip a kind prefix such as `model:` after checking it matches the resource.
pub fn normalize_lineage_target(
    target: &str,
    lookup: &dyn Fn(&str) -> Option<LineageKey>,
) -> Result<String, LineageError> {
    let resolved: LineageTarget = resolve_lineage_target(target, lookup);
    if resolved.kind.is_none() {
        return Ok(target.to_owned());
    }
    if !resolved.kind_matches {
        return Err(unknown_lineage_target(target));
    }
    Ok(resolved.name)
}
