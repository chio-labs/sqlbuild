//! The explicit or default lookback of a microbatch model.

use sqlbuild_core::plan_display::errors::UnknownCursorGrain;
use sqlbuild_core::plan_display::main::effective_microbatch_batch_size::effective_microbatch_batch_size;

use crate::planner_strategy::constants::IDEMPOTENT_MICROBATCH_STRATEGIES;
use crate::planner_strategy::models::LookbackConfig;

/// The authored lookback, else one batch at the replay grain for idempotent strategies.
pub fn microbatch_lookback(config: &LookbackConfig) -> Result<Option<String>, UnknownCursorGrain> {
    if let Some(lookback) = &config.lookback {
        return Ok(Some(lookback.clone()));
    }
    let idempotent: bool = config
        .incremental_strategy
        .as_deref()
        .is_some_and(|strategy| IDEMPOTENT_MICROBATCH_STRATEGIES.contains(&strategy));
    let (true, Some(batch_size)) = (idempotent, &config.batch_size) else {
        return Ok(None);
    };
    match &config.grain {
        Some(grain) => effective_microbatch_batch_size(batch_size, grain).map(Some),
        None => Ok(Some(batch_size.clone())),
    }
}
