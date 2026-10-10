//! The dynamic pivot proof a finished analysis session kept for one model.

use crate::assembly::analysis_session::models::{ContractProof, FinishedSession};

/// The named model's proof from the session's relation facts, or None where it declares none.
pub fn finished_dynamic_proof<'a>(
    session: &'a FinishedSession,
    name: &str,
) -> Option<&'a ContractProof> {
    session.dynamic_proofs.get(name)
}
