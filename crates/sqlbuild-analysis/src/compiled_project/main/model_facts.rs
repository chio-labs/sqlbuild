use crate::compiled_project::models::{CompiledModelFacts, CompiledProjectFacts};

/// The facts recorded for the model named `name`.
pub fn model_facts<'project>(
    project: &'project CompiledProjectFacts,
    name: &str,
) -> Option<&'project CompiledModelFacts> {
    project.model(name)
}
