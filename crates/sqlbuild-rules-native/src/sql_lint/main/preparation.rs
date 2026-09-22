//! Native lexical preparation with Python-compatible ASCII offsets.

use crate::sql_lint::types::PreparedSql;

pub(crate) fn prepare(
    expanded: &str,
    before_expansion: &str,
    prior_sites: &[usize],
) -> Result<Option<PreparedSql>, String> {
    crate::sql_lint::_helpers::preparation::prepare(expanded, before_expansion, prior_sites)
}
