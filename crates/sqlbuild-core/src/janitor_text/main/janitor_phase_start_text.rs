//! The announcement of one janitor apply phase.

use crate::janitor_text::_helpers::phases::{noun, phase_words};
use crate::janitor_text::models::JanitorPhase;

/// `Archiving 608 relations...`.
#[must_use]
pub fn janitor_phase_start_text(phase: JanitorPhase, total: usize) -> String {
    let (doing, _, singular) = phase_words(phase);
    format!("{doing} {}...", noun(total, singular))
}
