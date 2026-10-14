//! The SQL a local scenario replay writes under `target/run/scenarios/<name>/local/`.

use std::path::Path;

use crate::scenario_command::_helpers::paths::{
    function_output_path, model_output_path, safe_file_stem,
};
use crate::scenario_command::_helpers::statements::{expectation_artifacts, statements_text};
use crate::scenario_command::constants::FIXTURES_DIR;
use crate::scenario_command::models::{LocalRuntimeInputs, RuntimeArtifact};

/// Loaded snapshot tables, created functions, model SQL, then expectations.
#[must_use]
pub fn build_local_runtime_artifacts(inputs: &LocalRuntimeInputs) -> Vec<RuntimeArtifact> {
    let mut artifacts: Vec<RuntimeArtifact> = Vec::new();
    for relation in &inputs.loaded_relations {
        artifacts.push(RuntimeArtifact {
            relative_path: Path::new(FIXTURES_DIR).join(format!(
                "{}__{}.sql",
                relation.kind,
                safe_file_stem(&relation.logical_name)
            )),
            sql: format!(
                "-- loaded from {path}\n-- rows: {rows}\nCREATE TABLE \"{table}\" AS SELECT * FROM '{path}';",
                path = relation.file_path,
                rows = relation.row_count,
                table = relation.table_name
            ),
        });
    }
    for function in &inputs.functions {
        artifacts.push(RuntimeArtifact {
            relative_path: function_output_path(&function.relative_path, &function.language),
            sql: statements_text(&function.statements),
        });
    }
    for (relative_path, sql) in &inputs.models {
        artifacts.push(RuntimeArtifact {
            relative_path: model_output_path(relative_path),
            sql: sql.clone(),
        });
    }
    artifacts.extend(expectation_artifacts(&inputs.expectations));
    artifacts
}
