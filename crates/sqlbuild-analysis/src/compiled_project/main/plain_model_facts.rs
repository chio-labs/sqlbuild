use crate::compiled_project::models::{CompiledModelFacts, PlainModel};

/// A natively finished model's retained facts.
pub fn plain_model_facts(model: PlainModel) -> CompiledModelFacts {
    crate::compiled_project::_helpers::plain::plain_model_facts(model)
}
