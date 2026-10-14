use std::collections::BTreeSet;

use crate::graph::errors::SelectorError;
use crate::planner_selection::models::{
    SelectableModel, UnitTestSelectorNames, UnitTestSelectorSplit,
};

pub(super) fn texts(values: &[&str]) -> Vec<String> {
    values.iter().map(|value| (*value).to_owned()).collect()
}

pub(super) fn name_set(values: &[&str]) -> BTreeSet<String> {
    values.iter().map(|value| (*value).to_owned()).collect()
}

/// Unit tests `test_orders` and `test_customers`; resources `orders` and `customers`.
pub(super) fn selector_names() -> UnitTestSelectorNames {
    UnitTestSelectorNames {
        tests: name_set(&["test_customers", "test_orders"]),
        resources: name_set(&["customers", "orders"]),
    }
}

pub(super) fn split(
    select: &[&str],
    tests: &[&str],
    models_selected: bool,
) -> UnitTestSelectorSplit {
    UnitTestSelectorSplit {
        select: texts(select),
        exclude: Vec::new(),
        test_names: name_set(tests),
        excluded_test_names: BTreeSet::new(),
        models_selected,
    }
}

pub(super) fn failure(code: &'static str, message: &str, help: Option<&str>) -> SelectorError {
    SelectorError {
        code,
        message: message.to_owned(),
        help: help.map(str::to_owned),
    }
}

pub(super) fn models() -> Vec<SelectableModel> {
    let model = |name: &str, tags: &[&str], folder: &str| SelectableModel {
        name: name.to_owned(),
        tags: texts(tags),
        folder: folder.to_owned(),
    };
    vec![
        model("orders", &["daily"], "models/staging"),
        model("customers", &[], "models/staging/sub"),
        model("report", &["daily"], "models/marts"),
    ]
}
