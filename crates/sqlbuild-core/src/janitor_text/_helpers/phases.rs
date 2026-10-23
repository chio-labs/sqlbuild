//! Wording and durations of janitor apply phases.

use crate::cli_text::main::format_count_noun::format_count_noun;
use crate::janitor_text::constants::{MINUTE_SECONDS, SECONDS_PER_HOUR, SECONDS_PER_MINUTE};
use crate::janitor_text::models::JanitorPhase;

/// The phase's present participle, past tense and singular noun.
pub(crate) fn phase_words(phase: JanitorPhase) -> (&'static str, &'static str, &'static str) {
    match phase {
        JanitorPhase::DeleteRelations => ("Deleting", "Deleted", "relation"),
        JanitorPhase::Archive => ("Archiving", "Archived", "relation"),
        JanitorPhase::DeleteArchives => ("Deleting", "Deleted", "expired archive"),
        JanitorPhase::DropOldNameViews => ("Dropping", "Dropped", "old-name view"),
        JanitorPhase::DropQueryArtifacts => ("Dropping", "Dropped", "query artifact"),
        JanitorPhase::DropReviewSchemas => ("Dropping", "Dropped", "review schema"),
        JanitorPhase::PruneDirectState => ("Pruning", "Pruned", "direct state table"),
    }
}

/// `count` with the singular noun for one and its plural otherwise.
pub(crate) fn noun(count: usize, singular: &str) -> String {
    format_count_noun(i64::try_from(count).unwrap_or(i64::MAX), singular, None)
}

/// Seconds with two decimals under a minute, then whole minutes and seconds.
pub(crate) fn duration(seconds: f64) -> String {
    if seconds < MINUTE_SECONDS {
        return format!("{:.2}s", seconds.max(0.0));
    }
    let whole: u64 = seconds.round() as u64;
    let (hours, minutes, rest) = (
        whole / SECONDS_PER_HOUR,
        whole % SECONDS_PER_HOUR / SECONDS_PER_MINUTE,
        whole % SECONDS_PER_MINUTE,
    );
    if hours > 0 {
        return format!("{hours}h {minutes:02}m {rest:02}s");
    }
    format!("{minutes}m {rest:02}s")
}

/// `name -> destination`, or the name alone.
pub(crate) fn flow(name: &str, destination: Option<&str>) -> String {
    destination.map_or_else(
        || name.to_owned(),
        |destination| format!("{name} -> {destination}"),
    )
}
