use crate::plan_display::models::ModelLabelFacts;

/// A planned model with only its materialization and action.
pub(super) fn facts(materialization_type: &str, action: &str) -> ModelLabelFacts {
    ModelLabelFacts {
        materialization_type: materialization_type.to_owned(),
        action: action.to_owned(),
        ..ModelLabelFacts::default()
    }
}
