//! Read `[kind:]<name>` or `[kind:]<model>.<column>` against project resource names.

use crate::lineage_command::constants::{
    COLUMN_TARGET_KIND, COLUMN_TARGET_SEPARATOR, KIND_SEPARATOR, MODEL_RESOURCE_TYPE, TARGET_KINDS,
};
use crate::lineage_command::models::{LineageKey, LineageTarget};

/// The target's written kind, name, resource and column, and whether the kind fits the resource.
pub fn resolve_lineage_target(
    target: &str,
    lookup: &dyn Fn(&str) -> Option<LineageKey>,
) -> LineageTarget {
    let written_kind: Option<&str> = target
        .split_once(KIND_SEPARATOR)
        .map(|(kind, _)| kind)
        .filter(|kind| TARGET_KINDS.contains(kind));
    let name: &str = match written_kind {
        Some(kind) => &target[kind.len() + 1..],
        None => target,
    };
    let (resource_name, column_name): (&str, Option<&str>) =
        match name.split_once(COLUMN_TARGET_SEPARATOR) {
            Some((resource, column)) => (resource, Some(column)),
            None => (name, None),
        };
    let key: Option<LineageKey> = lookup(resource_name);
    let kind_matches: bool = match written_kind {
        None => true,
        Some(COLUMN_TARGET_KIND) => {
            key.as_ref()
                .is_some_and(|key| key.resource_type == MODEL_RESOURCE_TYPE)
                && column_name.is_some_and(|column| !column.is_empty())
        }
        Some(kind) => key.as_ref().is_some_and(|key| key.resource_type == kind),
    };
    LineageTarget {
        kind: written_kind.map(str::to_owned),
        name: name.to_owned(),
        key,
        column_name: column_name.map(str::to_owned),
        kind_matches,
    }
}
