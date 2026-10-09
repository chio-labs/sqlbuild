//! The models whose output names and lineage a finished analysis session kept.

use crate::assembly::analysis_session::models::FinishedSession;

/// Names of the models whose facts the session kept, in no particular order.
pub fn finished_fact_models(session: &FinishedSession) -> Vec<String> {
    session.models.keys().cloned().collect()
}
