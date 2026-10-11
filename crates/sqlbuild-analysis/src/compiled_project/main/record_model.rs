use crate::compiled_project::models::{CompiledModelFacts, CompiledProjectFacts};

/// Retain one model's compile-input facts; recording a name again replaces its facts in place.
pub fn record_model(project: &mut CompiledProjectFacts, model: CompiledModelFacts) {
    project.record_model(model);
}
