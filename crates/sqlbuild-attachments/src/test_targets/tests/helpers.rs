use crate::test_targets::models::{ScenarioCteSources, TargetGroup};

pub(super) fn cte(name: &str, check: bool, sources: &[&str]) -> ScenarioCteSources {
    ScenarioCteSources {
        name: name.to_owned(),
        check,
        sources: sources.iter().map(|source| (*source).to_owned()).collect(),
    }
}

pub(super) fn group(phrase: &str, names: &[&str], known: &[&str]) -> TargetGroup {
    TargetGroup {
        phrase: phrase.to_owned(),
        names: names.iter().map(|name| (*name).to_owned()).collect(),
        known: known.iter().map(|name| (*name).to_owned()).collect(),
    }
}
