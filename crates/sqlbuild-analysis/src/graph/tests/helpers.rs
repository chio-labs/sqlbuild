use crate::assembly::project::types::ObjectKey;
use crate::graph::errors::SelectorError;
use crate::graph::main::build_project_graph::build_project_graph;
use crate::graph::main::resolve_selectors::resolve_selectors;
use crate::graph::models::{GraphResource, ProjectGraph};
use crate::graph::tests::test_types::SelectorFailure;

type OwnedFailure = (String, String, Option<String>);

type ResourceSpec = (
    &'static str,
    &'static str,
    &'static [(&'static str, &'static str)],
    &'static [&'static str],
    Option<&'static str>,
);

/// Models, a source, a seed and a UDF with tags and folders, in Python's project order.
const ORDERS_PROJECT: &[ResourceSpec] = &[
    (
        "model",
        "orders",
        &[("source", "raw_orders"), ("udf", "tax")],
        &["daily"],
        Some("mart"),
    ),
    (
        "model",
        "order_items",
        &[("model", "orders"), ("seed", "countries")],
        &["daily", "finance"],
        Some("models/mart/items"),
    ),
    ("model", "customers", &[], &[], Some("staging/crm")),
    (
        "model",
        "customer_orders",
        &[("model", "customers"), ("model", "orders")],
        &[],
        Some("models"),
    ),
    ("source", "raw_orders", &[], &[], None),
    ("seed", "countries", &[], &["ref"], None),
    ("udf", "tax", &[], &[], None),
];

pub(super) fn key(pair: &(&str, &str)) -> ObjectKey {
    (pair.0.to_owned(), pair.1.to_owned())
}

pub(super) fn orders_graph() -> ProjectGraph {
    let resources: Vec<GraphResource> = ORDERS_PROJECT
        .iter()
        .map(|(kind, name, deps, tags, folder)| GraphResource {
            key: key(&(kind, name)),
            deps: deps.iter().map(key).collect(),
            tags: tags.iter().map(|tag| (*tag).to_owned()).collect(),
            folder: folder.map(str::to_owned),
        })
        .collect();
    build_project_graph(&resources)
}

/// The resolved keys, or the error's `(code, message, help)`.
pub(super) fn resolved(select: &[&str], exclude: &[&str]) -> Result<Vec<ObjectKey>, OwnedFailure> {
    let owned = |values: &[&str]| {
        values
            .iter()
            .map(|value| (*value).to_owned())
            .collect::<Vec<_>>()
    };
    resolve_selectors(&orders_graph(), &owned(select), &owned(exclude)).map_err(
        |SelectorError {
             code,
             message,
             help,
         }| (code.to_owned(), message, help),
    )
}

/// The keys a selector case expects.
pub(super) fn keys(pairs: &[(&str, &str)]) -> Vec<ObjectKey> {
    pairs.iter().map(key).collect()
}

/// An owned copy of the `(code, message, help)` a selector case expects.
pub(super) fn failure((code, message, help): SelectorFailure) -> OwnedFailure {
    (code.to_owned(), message.to_owned(), help.map(str::to_owned))
}
