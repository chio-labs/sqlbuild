//! The cause a command reports when it fails through its exit code instead of raising, for the invocation's terminal event.

use std::cell::RefCell;

/// A failure's error type, code and short message.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct FailureCause {
    pub(crate) error_type: String,
    pub(crate) error_code: String,
    pub(crate) message: String,
}

thread_local! {
    /// Per thread, since an invocation dispatches and reports on the thread that runs it, so concurrent invocations never read each other's cause.
    static FAILURE_CAUSE: RefCell<Option<FailureCause>> = const { RefCell::new(None) };
}

/// Record why the running command is about to return a failing exit code.
pub(crate) fn report_failure_cause(cause: FailureCause) {
    FAILURE_CAUSE.with(|slot| *slot.borrow_mut() = Some(cause));
}

/// The cause the command reported, cleared so the next invocation starts without one.
pub(crate) fn take_failure_cause() -> Option<FailureCause> {
    FAILURE_CAUSE.with(|slot| slot.borrow_mut().take())
}
