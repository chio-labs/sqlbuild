use crate::load_command::models::{LoadEntry, LoadGraph, LoadResultText, LoadStatus};

fn owned(names: &[&str]) -> Vec<String> {
    names.iter().map(|name| (*name).to_owned()).collect()
}

/// `fetch_events` and `fetch_prices` feed `raw_orders`; `raw_customers` and `raw_regions` stand alone.
pub(super) fn chained_graph() -> LoadGraph {
    LoadGraph {
        sources: vec![
            ("raw_orders".to_owned(), "raw_orders".to_owned()),
            ("raw_customers".to_owned(), "load_customers".to_owned()),
            ("raw_regions".to_owned(), "load_customers".to_owned()),
        ],
        loaders: vec![
            ("fetch_events".to_owned(), Vec::new()),
            ("fetch_prices".to_owned(), owned(&["fetch_events"])),
            (
                "raw_orders".to_owned(),
                owned(&["fetch_events", "fetch_prices"]),
            ),
            ("load_customers".to_owned(), Vec::new()),
        ],
    }
}

pub(super) fn loader(name: &str) -> LoadEntry {
    LoadEntry::Loader(name.to_owned())
}

pub(super) fn source(name: &str) -> LoadEntry {
    LoadEntry::Source(name.to_owned())
}

pub(super) fn selectors(names: &[&str]) -> Vec<String> {
    owned(names)
}

/// A finished source load with no logs, warnings or error.
pub(super) fn result(name: &str, status: LoadStatus) -> LoadResultText {
    LoadResultText {
        source_name: name.to_owned(),
        loader_name: name.to_owned(),
        resource_kind: "source".to_owned(),
        status,
        rows_loaded: 0,
        duration_ms: None,
        log_messages: Vec::new(),
        error_message: None,
        warning_messages: Vec::new(),
    }
}
