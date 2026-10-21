//! The cause a command reports when it fails through its exit code instead of raising, for the invocation's terminal event.

use std::sync::Mutex;

/// A failure's error type, code and short message.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct FailureCause {
    pub(crate) error_type: String,
    pub(crate) error_code: String,
    pub(crate) message: String,
}

static FAILURE_CAUSE: Mutex<Option<FailureCause>> = Mutex::new(None);

/// Record why the running command is about to return a failing exit code.
pub(crate) fn report_failure_cause(cause: FailureCause) {
    if let Ok(mut slot) = FAILURE_CAUSE.lock() {
        *slot = Some(cause);
    }
}

/// The cause the command reported, cleared so the next invocation starts without one.
pub(crate) fn take_failure_cause() -> Option<FailureCause> {
    FAILURE_CAUSE.lock().ok().and_then(|mut slot| slot.take())
}
