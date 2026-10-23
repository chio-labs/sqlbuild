use std::collections::{BTreeMap, BTreeSet};

use crate::definition_changes::constants::DEFINITION_SNAPSHOT_FORMAT;
use crate::definition_changes::main::node_key::node_key;
use crate::definition_changes::models::{DefinitionSnapshot, ExecutedItem, NodeDefinition};

/// One node with `aspects` as `(aspect, digest)` and `uses` as node keys.
pub(super) fn node(
    kind: &str,
    name: &str,
    aspects: &[(&str, &str)],
    uses: &[&str],
) -> (String, NodeDefinition) {
    (
        node_key(kind, name),
        NodeDefinition {
            kind: kind.to_owned(),
            name: name.to_owned(),
            aspects: aspects
                .iter()
                .map(|(aspect, digest)| ((*aspect).to_owned(), (*digest).to_owned()))
                .collect(),
            uses: uses.iter().map(|key| (*key).to_owned()).collect(),
            migrate_from: Vec::new(),
        },
    )
}

/// `definition` renamed from `old_names`.
pub(super) fn renamed(
    (key, mut definition): (String, NodeDefinition),
    old_names: &[&str],
) -> (String, NodeDefinition) {
    definition.migrate_from = old_names.iter().map(|name| (*name).to_owned()).collect();
    (key, definition)
}

pub(super) fn snapshot(nodes: Vec<(String, NodeDefinition)>) -> DefinitionSnapshot {
    DefinitionSnapshot {
        format: DEFINITION_SNAPSHOT_FORMAT,
        nodes: nodes.into_iter().collect::<BTreeMap<_, _>>(),
    }
}

/// The orders project at its base revision.
pub(super) fn base_orders() -> DefinitionSnapshot {
    snapshot(vec![
        node(
            "model",
            "stg_orders",
            &[("sql", "s1"), ("config", "c1"), ("columns", "k1")],
            &["macro:to_utc"],
        ),
        node(
            "model",
            "orders",
            &[("sql", "s2"), ("config", "c2")],
            &["enum:order_status"],
        ),
        node("model", "old_customers", &[("sql", "s3")], &[]),
        node("seed", "countries", &[("definition", "d1")], &[]),
        node(
            "macro",
            "to_utc",
            &[("definition", "m1")],
            &["macro:to_timestamp"],
        ),
        node("macro", "to_timestamp", &[("definition", "m2")], &[]),
        node("enum", "order_status", &[("definition", "e1")], &[]),
        node("test_file", "tests/orders.sql", &[("file", "t1")], &[]),
    ])
}

pub(super) fn keys(values: &[&str]) -> Vec<String> {
    values.iter().map(|value| (*value).to_owned()).collect()
}

/// The base orders project with `stg_orders` SQL edited, `customers` renamed and `countries` gone.
pub(super) fn current_orders() -> DefinitionSnapshot {
    snapshot(vec![
        node(
            "model",
            "stg_orders",
            &[("sql", "s1-edited"), ("config", "c1"), ("columns", "k1")],
            &["macro:to_utc"],
        ),
        node(
            "model",
            "orders",
            &[("sql", "s2"), ("config", "c2")],
            &["enum:order_status"],
        ),
        renamed(
            node("model", "customers", &[("sql", "s3")], &[]),
            &["old_customers"],
        ),
        node(
            "macro",
            "to_utc",
            &[("definition", "m1")],
            &["macro:to_timestamp"],
        ),
        node("macro", "to_timestamp", &[("definition", "m2")], &[]),
        node("enum", "order_status", &[("definition", "e1")], &[]),
        node("test_file", "tests/orders.sql", &[("file", "t1")], &[]),
    ])
}

/// What an item executes, by node keys.
pub(super) fn item(
    own: &[&str],
    executed: &[&str],
    declarations: &[&str],
    mocked: &[&str],
) -> ExecutedItem {
    ExecutedItem {
        own_keys: keys(own),
        executed: keys(executed),
        declarations: keys(declarations),
        mocked: mocked
            .iter()
            .map(|key| (*key).to_owned())
            .collect::<BTreeSet<_>>(),
        mocked_relations: Vec::new(),
    }
}

/// `current` with `entry` added or replaced.
pub(super) fn with_node(
    mut current: DefinitionSnapshot,
    entry: (String, NodeDefinition),
) -> DefinitionSnapshot {
    current.nodes.insert(entry.0, entry.1);
    current
}

/// `item` mocking the relations `keys`.
pub(super) fn mocking(mut item: ExecutedItem, keys: &[&str]) -> ExecutedItem {
    item.mocked_relations = keys.iter().map(|key| (*key).to_owned()).collect();
    item
}
