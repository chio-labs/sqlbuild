//! Python's builder and lookup sort keys, and grouping in Python's mapping order.

use crate::scope_index::_helpers::identities::{declaration_text, resource_text};
use crate::scope_index::_helpers::paths::normalize_path;
use crate::scope_index::models::{DeclarationRecord, KeyedGroups, ResourceRecord, ScopeDeferral};
use std::collections::HashMap;
use std::hash::Hash;

/// The builder's `_resource_key`.
pub(crate) fn resource_key(record: &ResourceRecord) -> (String, String) {
    (record.path.clone(), resource_text(&record.identity))
}

/// A declaration sort key: identity text, path, then line and column as `P` compares them.
#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub(crate) struct DeclarationKey<P> {
    identity: String,
    path: String,
    line: P,
    column: P,
}

/// The builder's `_declaration_key`, which compares line and column as integers.
pub(crate) fn declaration_key(record: &DeclarationRecord) -> DeclarationKey<i64> {
    DeclarationKey {
        identity: declaration_text(&record.identity),
        path: record.path.clone(),
        line: record.line,
        column: record.column,
    }
}

/// The lookup's `resource_sort_key`.
pub(crate) fn canonical_resource_key(
    record: &ResourceRecord,
) -> Result<(String, String), ScopeDeferral> {
    Ok((
        resource_text(&record.identity),
        normalize_path(&record.path)?,
    ))
}

/// The lookup's `declaration_sort_key`, which compares line and column as text.
pub(crate) fn canonical_declaration_key(
    record: &DeclarationRecord,
) -> Result<DeclarationKey<String>, ScopeDeferral> {
    Ok(DeclarationKey {
        identity: declaration_text(&record.identity),
        path: normalize_path(&record.path)?,
        line: record.line.to_string(),
        column: record.column.to_string(),
    })
}

/// Stable sort of `members` by a fallible key, as Python's `sorted(..., key=...)`.
pub(crate) fn sorted_by_key<K: Ord>(
    members: &[usize],
    key: impl Fn(usize) -> Result<K, ScopeDeferral>,
) -> Result<Vec<usize>, ScopeDeferral> {
    let mut keyed: Vec<(K, usize)> = members
        .iter()
        .map(|member| Ok((key(*member)?, *member)))
        .collect::<Result<_, ScopeDeferral>>()?;
    keyed.sort_by(|left, right| left.0.cmp(&right.0));
    Ok(keyed.into_iter().map(|(_key, member)| member).collect())
}

/// Members grouped by key, groups in first-occurrence order and members in input order.
pub(crate) fn group_in_order<K: Hash + Eq>(
    members: &[usize],
    key: impl Fn(usize) -> K,
) -> Vec<Vec<usize>> {
    let mut positions: HashMap<K, usize> = HashMap::new();
    let mut groups: Vec<Vec<usize>> = Vec::new();
    for member in members {
        let group_key: K = key(*member);
        match positions.get(&group_key) {
            Some(position) => groups[*position].push(*member),
            None => {
                positions.insert(group_key, groups.len());
                groups.push(vec![*member]);
            }
        }
    }
    groups
}

/// Python's `group_records`: groups ordered by `repr(key)`, members in input order.
pub(crate) fn keyed_groups<K: Hash + Eq>(
    members: &[usize],
    key: impl Fn(usize) -> K,
    repr: impl Fn(&K) -> String,
) -> KeyedGroups {
    let groups: Vec<Vec<usize>> = group_in_order(members, &key);
    let mut ordered: Vec<(String, Vec<usize>)> = groups
        .into_iter()
        .map(|group| (repr(&key(group[0])), group))
        .collect();
    ordered.sort_by(|left, right| left.0.cmp(&right.0));
    KeyedGroups {
        groups: ordered.into_iter().map(|(_repr, group)| group).collect(),
    }
}
