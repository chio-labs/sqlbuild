//! The message of a model planning more batches than its limit.

/// `None` within the limit; `cap` says whether the action caps (rather than fails or warns).
pub fn microbatch_limit_warning(
    model_name: &str,
    (max_batches, batch_count): (Option<i128>, i128),
    (action, cap): (&str, bool),
) -> Option<String> {
    let max_batches: i128 = max_batches.filter(|maximum| batch_count > *maximum)?;
    let follow_up: String = if cap {
        format!(
            "Selected {max_batches} batches and deferred {}.",
            batch_count - max_batches
        )
    } else {
        "Use --max-microbatches with an intentional invocation-specific value for this backfill."
            .to_owned()
    };
    Some(format!(
        "MICROBATCH LIMIT EXCEEDED: model '{model_name}' planned {batch_count} batches, above \
         the per-model limit of {max_batches} (action={action}). {follow_up}"
    ))
}
