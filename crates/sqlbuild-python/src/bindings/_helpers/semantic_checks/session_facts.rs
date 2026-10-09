//! Model output names and lineage the semantic stages read from a finished analysis session.

use sqlbuild_analysis::assembly::analysis_session::main::finished_model_facts::finished_model_facts;
use sqlbuild_analysis::assembly::analysis_session::models::SessionModelFacts;

use crate::bindings::_helpers::analysis_session::session::NativeModelAnalysisSession;

/// The facts the finished `session` kept for model `name`, which the payload left out.
pub(crate) fn session_model_facts<'a>(
    session: Option<&'a NativeModelAnalysisSession>,
    name: &str,
) -> Result<&'a SessionModelFacts, String> {
    let finished = session
        .and_then(NativeModelAnalysisSession::finished_session)
        .ok_or("a model asked for session facts without a finished session")?;
    finished_model_facts(finished, name)
        .ok_or_else(|| format!("the finished session kept no facts for model {name}"))
}
