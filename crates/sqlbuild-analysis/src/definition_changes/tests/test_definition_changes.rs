use std::collections::BTreeSet;

use crate::definition_changes::main::changes_summary::changes_summary;
use crate::definition_changes::main::compare_definitions::compare_definitions;
use crate::definition_changes::main::definition_digest::sql_definition_digest;
use crate::definition_changes::main::definition_snapshot_json::{
    definition_snapshot_json, parse_definition_snapshot,
};
use crate::definition_changes::main::selection_reasons::selection_reasons;
use crate::definition_changes::main::selection_report::selection_report;
use crate::definition_changes::models::{
    DefinitionChanges, DefinitionSnapshot, DeletedNode, ExecutedItem, NodeChange, SelectedItem,
};
use crate::definition_changes::tests::helpers::{base_orders, node, renamed, snapshot};
use crate::definition_changes::tests::test_types::SelectionReasonTestCase;

fn keys(values: &[&str]) -> Vec<String> {
    values.iter().map(|value| (*value).to_owned()).collect()
}

/// The base orders project with `stg_orders` SQL edited, `customers` renamed from
/// `old_customers` and `countries` deleted.
fn current_orders() -> DefinitionSnapshot {
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

#[test]
fn given_two_snapshots_when_comparing_then_reports_changed_renamed_and_deleted_nodes() {
    let changes: DefinitionChanges = compare_definitions(&base_orders(), &current_orders());

    assert_eq!(
        changes.changed.into_iter().collect::<Vec<_>>(),
        vec![(
            "model:stg_orders".to_owned(),
            NodeChange {
                kind: "model".to_owned(),
                name: "stg_orders".to_owned(),
                added: false,
                aspects: keys(&["sql"]),
                renamed_from: None,
            }
        )]
    );
    assert_eq!(
        changes.renamed,
        vec![(
            "model:old_customers".to_owned(),
            "model:customers".to_owned()
        )]
    );
    assert_eq!(
        changes.deleted,
        vec![DeletedNode {
            kind: "seed".to_owned(),
            name: "countries".to_owned(),
        }]
    );
}

#[test]
fn given_renamed_node_with_edited_definition_when_comparing_then_it_changed_from_old_name() {
    let base = snapshot(vec![node("model", "old_customers", &[("sql", "s3")], &[])]);
    let current = snapshot(vec![renamed(
        node(
            "model",
            "customers",
            &[("sql", "s4"), ("config", "c4")],
            &[],
        ),
        &["old_customers"],
    )]);

    let changes: DefinitionChanges = compare_definitions(&base, &current);

    let change: &NodeChange = &changes.changed["model:customers"];
    assert_eq!(change.renamed_from.as_deref(), Some("old_customers"));
    assert_eq!(change.aspects, keys(&["sql", "config"]));
    assert!(changes.deleted.is_empty());
}

#[test]
fn given_changes_when_summarising_then_counts_each_kind_and_names_deleted_nodes() {
    let mut current: DefinitionSnapshot = current_orders();
    current.nodes.extend([
        node("model", "returns", &[("sql", "s9")], &[]),
        node("macro", "to_timestamp", &[("definition", "m3")], &[]),
    ]);

    let summary: String = changes_summary(&compare_definitions(&base_orders(), &current));

    assert_eq!(
        summary,
        "1 model, 1 macro changed; 1 model added; 1 model renamed; deleted: seed countries"
    );
    assert_eq!(
        changes_summary(&compare_definitions(&base_orders(), &base_orders())),
        "no definition changes"
    );
}

fn item(own: &[&str], executed: &[&str], declarations: &[&str], mocked: &[&str]) -> ExecutedItem {
    ExecutedItem {
        own_keys: keys(own),
        executed: keys(executed),
        declarations: keys(declarations),
        mocked: mocked
            .iter()
            .map(|key| (*key).to_owned())
            .collect::<BTreeSet<_>>(),
    }
}

fn with_node(
    mut current: DefinitionSnapshot,
    entry: (String, crate::definition_changes::models::NodeDefinition),
) -> DefinitionSnapshot {
    current.nodes.insert(entry.0, entry.1);
    current
}

#[test]
fn given_executed_item_when_explaining_selection_then_lists_each_changed_dependency() {
    let test_cases = [
        SelectionReasonTestCase {
            description: "an executed model whose SQL changed",
            current: current_orders(),
            item: item(
                &["test_file:tests/orders.sql"],
                &["model:stg_orders", "model:orders"],
                &[],
                &[],
            ),
            expected_reasons: &["executes stg_orders (model SQL changed)"],
        },
        SelectionReasonTestCase {
            description: "a mocked model is not executed, so its change selects nothing",
            current: current_orders(),
            item: item(&["test_file:tests/orders.sql"], &["model:orders"], &[], &[]),
            expected_reasons: &[],
        },
        SelectionReasonTestCase {
            description: "a macro changed through another macro the model calls",
            current: with_node(
                snapshot(base_orders().nodes.into_iter().collect()),
                node("macro", "to_timestamp", &[("definition", "m3")], &[]),
            ),
            item: item(&[], &["model:stg_orders"], &[], &[]),
            expected_reasons: &["executes macro to_timestamp (changed)"],
        },
        SelectionReasonTestCase {
            description: "a mocked macro hides its own and its callees' changes",
            current: with_node(
                snapshot(base_orders().nodes.into_iter().collect()),
                node("macro", "to_timestamp", &[("definition", "m3")], &[]),
            ),
            item: item(&[], &["model:stg_orders"], &[], &["macro:to_utc"]),
            expected_reasons: &[],
        },
        SelectionReasonTestCase {
            description: "an enum used by an executed model",
            current: with_node(
                snapshot(base_orders().nodes.into_iter().collect()),
                node("enum", "order_status", &[("definition", "e2")], &[]),
            ),
            item: item(&[], &["model:orders"], &[], &[]),
            expected_reasons: &["uses enum order_status (changed)"],
        },
        SelectionReasonTestCase {
            description: "the test's own file and an added model",
            current: with_node(
                with_node(
                    snapshot(base_orders().nodes.into_iter().collect()),
                    node("test_file", "tests/orders.sql", &[("file", "t2")], &[]),
                ),
                node("model", "returns", &[("sql", "s9")], &[]),
            ),
            item: item(
                &["test_file:tests/orders.sql"],
                &["model:returns"],
                &[],
                &[],
            ),
            expected_reasons: &["test file changed", "executes returns (added)"],
        },
        SelectionReasonTestCase {
            description: "a renamed model whose config changed",
            current: snapshot(vec![renamed(
                node(
                    "model",
                    "customers",
                    &[("sql", "s3"), ("config", "c9")],
                    &[],
                ),
                &["old_customers"],
            )]),
            item: item(&[], &["model:customers"], &[], &[]),
            expected_reasons: &[
                "executes customers (renamed from old_customers, model config changed)",
            ],
        },
        SelectionReasonTestCase {
            description: "a changed seed the test really reads",
            current: with_node(
                snapshot(base_orders().nodes.into_iter().collect()),
                node("seed", "countries", &[("definition", "d2")], &[]),
            ),
            item: item(&[], &["model:orders", "seed:countries"], &[], &[]),
            expected_reasons: &["executes seed countries (changed)"],
        },
    ];
    for test_case in test_cases {
        let changes: DefinitionChanges = compare_definitions(&base_orders(), &test_case.current);

        let reasons: Vec<String> = selection_reasons(&test_case.item, &test_case.current, &changes);

        assert_eq!(
            reasons,
            keys(test_case.expected_reasons),
            "{}",
            test_case.description
        );
    }
}

#[test]
fn given_snapshot_when_stored_then_reads_back_only_in_the_same_format() {
    let snapshot: DefinitionSnapshot = base_orders();
    let stored: String = definition_snapshot_json(&snapshot);

    assert_eq!(parse_definition_snapshot(&stored), Some(snapshot));
    assert_eq!(
        parse_definition_snapshot(&stored.replacen("\"format\":1", "\"format\":0", 1)),
        None
    );
    assert_eq!(parse_definition_snapshot("not json"), None);
}

#[test]
fn given_sql_when_fingerprinting_definition_then_ignores_layout_and_comments_only() {
    let original: String = sql_definition_digest("SELECT order_id FROM orders");

    assert_eq!(
        sql_definition_digest("select\n  order_id -- the key\nfrom orders"),
        original
    );
    assert_ne!(
        sql_definition_digest("SELECT customer_id FROM orders"),
        original
    );
}

#[test]
fn given_selected_items_when_reporting_then_counts_and_explains_only_on_request() {
    let selected = [SelectedItem {
        label: "orders_rollup".to_owned(),
        reasons: keys(&["executes stg_orders (model SQL changed)"]),
    }];

    assert_eq!(
        selection_report(
            ("origin/main", "1 model changed"),
            ("test", "tests"),
            (9, &selected),
            true
        ),
        "Changed since origin/main: 1 model changed\nSelected 1 of 9 tests\n  orders_rollup\n    \
         executes stg_orders (model SQL changed)\n"
    );
    assert_eq!(
        selection_report(
            ("origin/main", "1 model changed"),
            ("test", "tests"),
            (9, &selected),
            false
        ),
        "Changed since origin/main: 1 model changed\nSelected 1 of 9 tests\n"
    );
    assert_eq!(
        selection_report(
            ("origin/main", "no definition changes"),
            ("scenario", "scenarios"),
            (3, &[]),
            true
        ),
        "Changed since origin/main: no definition changes\nNo scenarios are affected by the \
         changes since origin/main\n"
    );
}
