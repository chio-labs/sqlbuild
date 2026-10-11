use sqlbuild_analysis::compiled_project::main::model_facts::model_facts;
use sqlbuild_analysis::compiled_project::models::CompiledProjectFacts;

use crate::models::ModelRow;

/// Rules rows for `names` in that order, read from the project's retained model facts.
pub fn project_model_rows(
    project: &CompiledProjectFacts,
    names: &[String],
) -> Result<Vec<ModelRow>, String> {
    names
        .iter()
        .map(|name| {
            model_facts(project, name)
                .ok_or_else(|| format!("compiled model '{name}' has no retained compile facts"))
                .and_then(crate::engine::_helpers::project_rows::model_row)
        })
        .collect()
}
