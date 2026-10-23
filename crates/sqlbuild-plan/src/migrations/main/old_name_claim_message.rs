//! Diagnostics for attempts to replace a recorded compatibility view.

/// Describe the cleanup needed before a model can claim an old name.
pub fn old_name_claim_message(
    model: &str,
    relation: (&str, &str),
    expiration: (Option<&str>, bool),
) -> String {
    let (name, destination) = relation;
    let (date, expired) = expiration;
    if let Some(date) = date
        && expired
    {
        return format!(
            "model '{model}' would replace {name}, a compatibility view for model:{destination} that expired {date}; run `sqb janitor` to drop it first"
        );
    }
    let until = date
        .map(|date| format!(" until {date}"))
        .unwrap_or_default();
    format!(
        "model '{model}' would replace {name}, a compatibility view for model:{destination}{until}; drop it early with `sqb janitor --drop-old-name-view {name}`"
    )
}
