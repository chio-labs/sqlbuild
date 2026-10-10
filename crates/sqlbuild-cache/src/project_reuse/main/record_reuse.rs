use crate::project_reuse::errors::ReuseRecordError;
use crate::project_reuse::models::{CompileRecord, RecordResult, ReuseAttempt, ReuseRules};

/// Store a reusable full compile, or clear the slot when this compile cannot be reused.
pub fn record_reuse(
    attempt: &ReuseAttempt,
    record: &CompileRecord,
    rules: &ReuseRules,
) -> Result<RecordResult, ReuseRecordError> {
    crate::project_reuse::_helpers::attempt::record(attempt, record, rules)
}
