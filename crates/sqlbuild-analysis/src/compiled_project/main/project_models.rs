use crate::compiled_project::models::{CompiledModelFacts, CompiledProjectFacts};

/// Every recorded model's facts, in production order.
pub fn project_models(project: &CompiledProjectFacts) -> &[CompiledModelFacts] {
    &project.models
}
