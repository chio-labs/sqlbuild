use std::collections::HashSet;

use crate::test_targets::models::{ScenarioCteSources, TargetCatalog};

pub(super) fn cte(name: &str, check: bool, sources: &[&str]) -> ScenarioCteSources {
    ScenarioCteSources {
        name: name.to_owned(),
        check,
        sources: sources.iter().map(|source| (*source).to_owned()).collect(),
    }
}

pub(super) fn names(values: &[&str]) -> Vec<String> {
    values.iter().map(|value| (*value).to_owned()).collect()
}

/// Models `orders` and `customers`, seed `regions` and source `raw`.
pub(super) fn catalog() -> TargetCatalog {
    TargetCatalog {
        models: names(&["orders", "customers"]).into_iter().collect(),
        sources: HashSet::from(["raw".to_owned()]),
        seeds: HashSet::from(["regions".to_owned()]),
        ..TargetCatalog::default()
    }
}
