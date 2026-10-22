//! The close of a janitor apply phase that an action stopped.

use crate::cli_text::main::format_phase_line::format_phase_line;
use crate::cli_text::models::CliStyle;
use crate::janitor_text::_helpers::phases::{duration, noun, phase_words};
use crate::janitor_text::models::JanitorPhase;

/// `✗ Archiving failed  after 11 of 608 relations  (1m 02s)`.
#[must_use]
pub fn janitor_phase_failed_text(
    phase: JanitorPhase,
    (completed, total): (usize, usize),
    elapsed_seconds: f64,
    style: CliStyle,
) -> String {
    let (doing, _, singular) = phase_words(phase);
    format_phase_line(
        style,
        false,
        (
            &format!("{doing} failed"),
            &format!(
                "after {completed} of {}  ({})",
                noun(total, singular),
                duration(elapsed_seconds)
            ),
        ),
    )
}
