//! Reject a local project-wide SQL analysis opt-out the project forbids.

use crate::project::errors::ConfigFailure;
use crate::project::models::ConfigPaths;

/// `validate_local_sql_analysis_policy` over (required, overridden, enabled) SQL analysis flags.
pub fn local_sql_analysis_failure(
    paths: &ConfigPaths,
    flags: (bool, bool, bool),
) -> Option<ConfigFailure> {
    crate::project::_helpers::documents::local_sql_analysis_failure(paths, flags)
}
