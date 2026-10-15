use crate::plan_display::models::{ModelLabelFacts, TimestampGrainFacts};

/// A planned model with only its materialization and action.
pub(super) fn facts(materialization_type: &str, action: &str) -> ModelLabelFacts {
    ModelLabelFacts {
        materialization_type: materialization_type.to_owned(),
        action: action.to_owned(),
        ..ModelLabelFacts::default()
    }
}

/// A timestamp cursor with the strategy, declared grain and input grains given.
pub(super) fn timestamp_grains(
    microbatch_strategy: Option<&str>,
    downstream_grain: Option<&str>,
    input_grains: &[Option<&str>],
) -> TimestampGrainFacts {
    TimestampGrainFacts {
        cursor_type: Some("timestamp".to_owned()),
        microbatch_strategy: microbatch_strategy.map(str::to_owned),
        downstream_grain: downstream_grain.map(str::to_owned),
        input_grains: input_grains
            .iter()
            .map(|grain| grain.map(str::to_owned))
            .collect(),
    }
}
