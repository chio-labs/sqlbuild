//! Scenario names, files and folders resolved to the scenarios they select.

use std::collections::BTreeSet;

use crate::scenario_command::_helpers::selection::{ScenarioPaths, selector_matches};
use crate::scenario_command::constants::NONE_DISCOVERED_CODE;
use crate::scenario_command::errors::ScenarioCommandError;
use crate::scenario_command::models::{ScenarioFile, ScenarioSelection};

/// Indices of the selected scenarios: every scenario without selectors, less the excluded ones.
pub fn select_scenarios(
    scenarios: &[ScenarioFile],
    selection: ScenarioSelection<'_>,
) -> Result<Vec<usize>, ScenarioCommandError> {
    let paths: Vec<ScenarioPaths> = scenarios.iter().map(ScenarioPaths::of).collect();
    let selected: Vec<usize> = if selection.selectors.is_empty() {
        if scenarios.is_empty() {
            return Err(ScenarioCommandError {
                code: NONE_DISCOVERED_CODE,
                message: "No SQL scenarios were discovered under tests/scenarios".to_owned(),
                help: None,
            });
        }
        (0..scenarios.len()).collect()
    } else {
        let mut selected: Vec<usize> = Vec::new();
        let mut names: BTreeSet<&str> = BTreeSet::new();
        for selector in selection.selectors {
            for index in selector_matches(scenarios, &paths, (selector, selection.project_dir))? {
                if names.insert(scenarios[index].name.as_str()) {
                    selected.push(index);
                }
            }
        }
        selected
    };
    if selection.exclude.is_empty() {
        return Ok(selected);
    }
    let mut excluded: BTreeSet<&str> = BTreeSet::new();
    for selector in selection.exclude {
        for index in selector_matches(scenarios, &paths, (selector, selection.project_dir))? {
            excluded.insert(scenarios[index].name.as_str());
        }
    }
    Ok(selected
        .into_iter()
        .filter(|index| !excluded.contains(scenarios[*index].name.as_str()))
        .collect())
}
