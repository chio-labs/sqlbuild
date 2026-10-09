//! The output names and lineage a finished analysis session kept for compiled models.

use crate::assembly::analysis_session::models::{FinishedSession, SessionModelFacts};

/// The named model's facts, or None where the session kept none for it.
pub fn finished_model_facts<'a>(
    session: &'a FinishedSession,
    name: &str,
) -> Option<&'a SessionModelFacts> {
    session.models.get(name)
}
