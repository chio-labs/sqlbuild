use crate::assembly::project::types::ObjectKey;
use crate::graph::main::build_project_graph::build_project_graph;
use crate::graph::main::resolve_selectors::resolve_selectors;
use crate::graph::models::{GraphResource, ProjectGraph, SelectorError};

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
        Some("mart/items"),
    ),
    ("model", "customers", &[], &[], Some("staging/crm")),
    (
        "model",
        "customer_orders",
        &[("model", "customers"), ("model", "orders")],
        &[],
        Some(""),
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
pub(super) fn resolved(
    select: &[&str],
    exclude: &[&str],
) -> Result<Vec<ObjectKey>, (String, String, Option<String>)> {
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

pub(super) fn expected(
    outcome: &Result<&[(&str, &str)], (&str, &str, Option<&str>)>,
) -> Result<Vec<ObjectKey>, (String, String, Option<String>)> {
    match outcome {
        Ok(keys) => Ok(keys.iter().map(key).collect()),
        Err((code, message, help)) => Err((
            (*code).to_owned(),
            (*message).to_owned(),
            help.map(str::to_owned),
        )),
    }
}
