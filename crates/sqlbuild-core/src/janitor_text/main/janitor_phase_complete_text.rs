//! The close of one janitor apply phase.

use crate::janitor_text::_helpers::phases::{duration, noun, phase_words};
use crate::janitor_text::constants::RECORDED_ACTION;
use crate::janitor_text::models::{JanitorItemText, JanitorPhase};

/// `Archived 608 relations. (4m 51s)`, also counting old-name views recorded as already gone.
#[must_use]
pub fn janitor_phase_complete_text(
    phase: JanitorPhase,
    items: &[JanitorItemText],
    elapsed_seconds: f64,
) -> String {
    let (_, done, singular) = phase_words(phase);
    let finished: Vec<&JanitorItemText> = items
        .iter()
        .filter(|item| item.phase == phase && item.error.is_none())
        .collect();
    let recorded: usize = finished
        .iter()
        .filter(|item| item.action == RECORDED_ACTION)
        .count();
    let recorded_text: String = if recorded == 0 {
        String::new()
    } else {
        format!(" and recorded {recorded} already gone")
    };
    format!(
        "{done} {}{recorded_text}. ({})",
        noun(finished.len() - recorded, singular),
        duration(elapsed_seconds)
    )
}
