//! Real models whose unmocked model inputs pull unmocked sources into a scenario.

use std::collections::{BTreeSet, HashMap};

use crate::planner_scenario::models::ScenarioGraphInput;

/// Whether `name`, run as a real model, reads a source the scenario does not mock, with the memo.
fn reaches_unmocked_source(
    name: &str,
    input: &ScenarioGraphInput,
    mut memo: HashMap<String, bool>,
) -> (bool, HashMap<String, bool>) {
    if let Some(known) = memo.get(name) {
        return (*known, memo);
    }
    memo.insert(name.to_owned(), false);
    let mut reaches: bool = false;
    for (kind, dep) in input.models.get(name).into_iter().flatten() {
        reaches = match kind.as_str() {
            "source" => !input.sources.contains(dep),
            "model" if !input.refs.contains(dep) => {
                let (found, updated) = reaches_unmocked_source(dep, input, memo);
                memo = updated;
                found
            }
            _ => false,
        };
        if reaches {
            break;
        }
    }
    memo.insert(name.to_owned(), reaches);
    (reaches, memo)
}

/// Real models that mock some model inputs but leave others, which read unmocked sources, real.
pub(crate) fn unmocked_boundaries(
    input: &ScenarioGraphInput,
    models: &BTreeSet<String>,
) -> Vec<String> {
    let mut memo: HashMap<String, bool> = HashMap::new();
    let mut messages: Vec<String> = Vec::new();
    for name in models {
        let Some(deps) = input.models.get(name) else {
            continue;
        };
        let model_deps = || {
            deps.iter()
                .filter(|(kind, _)| matches!(kind.as_str(), "model"))
        };
        if !model_deps().any(|(_, dep)| input.refs.contains(dep)) {
            continue;
        }
        let mut unmocked: Vec<&str> = Vec::new();
        for (_, dep) in model_deps() {
            if input.refs.contains(dep)
                || !input.models.contains_key(dep)
                || unmocked.contains(&dep.as_str())
            {
                continue;
            }
            let (reaches, updated) = reaches_unmocked_source(dep, input, memo);
            memo = updated;
            if reaches {
                unmocked.push(dep);
            }
        }
        if unmocked.is_empty() {
            continue;
        }
        let quoted: Vec<String> = unmocked.iter().map(|dep| format!("'{dep}'")).collect();
        let ctes: Vec<String> = unmocked
            .iter()
            .map(|dep| format!("__ref__{dep} AS (...)"))
            .collect();
        messages.push(format!(
            "Scenario '{}': model '{name}' reads {}, which {} not mocked, while its other model inputs are. Add {} named {}.",
            input.name,
            quoted.join(" and "),
            if unmocked.len() == 1 { "is" } else { "are" },
            if unmocked.len() == 1 { "a CTE" } else { "CTEs" },
            ctes.join(" and ")
        ));
    }
    messages
}
