//! The error for a target that names no project resource.

use crate::lineage_command::constants::GRAPH_OPERATORS;
use crate::lineage_command::errors::LineageError;

/// `unknown lineage target`, pointing at `--direction` when the target uses graph operators.
#[must_use]
pub(crate) fn unknown_lineage_target(target: &str) -> LineageError {
    let help: &str = if target.contains(GRAPH_OPERATORS) {
        "graph operators are not supported in lineage targets; \
         use --direction upstream|downstream|both and --depth N"
    } else {
        "use a model, source or seed name, optionally prefixed like model:orders"
    };
    LineageError::new("C305", &format!("unknown lineage target '{target}'")).with_help(help)
}
