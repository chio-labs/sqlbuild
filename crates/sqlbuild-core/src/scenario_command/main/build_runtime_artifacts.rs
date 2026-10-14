//! The SQL a warehouse scenario run writes under `target/run/scenarios/<name>/`.

use std::path::Path;

use crate::scenario_command::_helpers::paths::{model_output_path, safe_file_stem};
use crate::scenario_command::_helpers::statements::{expectation_artifacts, statements_artifact};
use crate::scenario_command::constants::{CLEANUP_DIR, FIXTURES_DIR, SEEDS_DIR};
use crate::scenario_command::models::{RuntimeArtifact, WarehouseRuntimeInputs};

/// Prepare cleanup, fixtures, seeds, models, expectations, then the final cleanup.
#[must_use]
pub fn build_runtime_artifacts(inputs: &WarehouseRuntimeInputs) -> Vec<RuntimeArtifact> {
    let cleanup = |file_name: &str, statements: &Option<Vec<String>>| {
        statements.as_ref().and_then(|statements| {
            statements_artifact(&Path::new(CLEANUP_DIR).join(file_name), statements)
        })
    };
    let fixtures = inputs.fixtures.iter().filter_map(|fixture| {
        statements_artifact(
            &Path::new(FIXTURES_DIR).join(format!(
                "{}__{}.sql",
                fixture.kind,
                safe_file_stem(&fixture.logical_name)
            )),
            &fixture.statements,
        )
    });
    let seeds = inputs.seeds.iter().filter_map(|seed| {
        statements_artifact(
            &Path::new(SEEDS_DIR).join(format!("{}.sql", seed.name)),
            &seed.statements,
        )
    });
    let mut models: Vec<RuntimeArtifact> = Vec::new();
    for model in &inputs.models {
        let Some(entry) = inputs
            .model_entries
            .iter()
            .find(|entry| entry.name == model.name)
        else {
            continue;
        };
        models.extend(statements_artifact(
            &model_output_path(&entry.relative_path),
            &model.statements,
        ));
    }
    cleanup("prepare.sql", &inputs.prepare_cleanup)
        .into_iter()
        .chain(fixtures)
        .chain(seeds)
        .chain(models)
        .chain(expectation_artifacts(&inputs.expectations))
        .chain(cleanup("final.sql", &inputs.final_cleanup))
        .collect()
}
