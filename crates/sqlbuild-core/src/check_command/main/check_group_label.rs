//! The output group of one check.

use crate::check_command::constants::{MULTI_DEPENDENCY_GROUP, UNGROUPED};
use crate::check_command::models::CheckGrouping;

/// The single dependency's name, else the declared group, else `multi-dependency` or `ungrouped`.
#[must_use]
pub fn check_group_label(grouping: &CheckGrouping) -> String {
    if let Some(dependencies) = &grouping.dependencies {
        if let [only] = dependencies.as_slice() {
            return only.clone();
        }
        if dependencies.len() > 1 {
            return grouping
                .group
                .clone()
                .unwrap_or_else(|| MULTI_DEPENDENCY_GROUP.to_owned());
        }
    }
    grouping
        .group
        .clone()
        .unwrap_or_else(|| UNGROUPED.to_owned())
}
