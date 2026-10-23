//! Whether the running command already printed its machine-readable document, so a failure adds no second one.

use std::cell::Cell;

thread_local! {
    /// Per thread, since an invocation dispatches and reports on the thread that runs it.
    static MACHINE_OUTPUT_WRITTEN: Cell<bool> = const { Cell::new(false) };
}

/// Record that the running command printed its machine-readable document on stdout.
pub(crate) fn report_machine_output_written() {
    MACHINE_OUTPUT_WRITTEN.with(|written| written.set(true));
}

/// Whether the running command printed its document, cleared for the next invocation.
pub(crate) fn take_machine_output_written() -> bool {
    MACHINE_OUTPUT_WRITTEN.with(|written| written.replace(false))
}
