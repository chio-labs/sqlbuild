//! `schema_age`: how a store's tables and views compare with this build's.

use std::collections::{BTreeMap, BTreeSet};

use crate::schema::models::SchemaAge;

/// Compare the `observed` columns of each table and view with this build's `expected` ones; both evolve additively, so a missing relation or column means an older store and an unknown column a newer one. When none of `views` is observed, the user may simply not see them, so nothing is judged. A relation this build does not define is ignored.
#[must_use]
pub fn schema_age(
    expected: &BTreeMap<&'static str, BTreeSet<String>>,
    observed: &BTreeMap<String, BTreeSet<String>>,
    views: &[&str],
) -> SchemaAge {
    if !views.iter().any(|view| observed.contains_key(*view)) {
        return SchemaAge::Unseen;
    }
    let mut older: bool = false;
    for (relation, columns) in expected {
        let Some(present) = observed.get(*relation) else {
            older = true;
            continue;
        };
        if present.difference(columns).next().is_some() {
            return SchemaAge::Newer;
        }
        older |= columns.difference(present).next().is_some();
    }
    if older {
        SchemaAge::Older
    } else {
        SchemaAge::Current
    }
}
