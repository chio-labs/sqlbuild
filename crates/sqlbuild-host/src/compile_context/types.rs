//! The timing collector handle, the process clock and the compile diagnostic sink.

use std::cell::RefCell;
use std::rc::Rc;

use sqlbuild_core::compile_timings::models::CompileTimings;

/// One compile invocation's collector, shared by every recorder on its thread.
pub type CompileTimingsHandle = Rc<RefCell<CompileTimings>>;

/// The process CPU clock, including worker threads, as the host reads it.
pub trait ProcessClock {
    /// Why the clock could not be read.
    type Error;

    /// The process CPU time in nanoseconds.
    fn process_time_ns(&self) -> Result<u64, Self::Error>;
}

/// The compile's diagnostic sink: the active collection, or the first error when none collects.
pub trait CompileDiagnosticSink {
    /// What identifies one diagnostic; a repeated key keeps the first diagnostic.
    type Key: ?Sized;
    /// One compile diagnostic.
    type Diagnostic: ?Sized;
    /// The failure a diagnostic becomes when no collection is active, or a reporting failure.
    type Error;

    /// Record `diagnostic` under `key` in the active collection, or fail with it when none is.
    fn report(&self, key: &Self::Key, diagnostic: &Self::Diagnostic) -> Result<(), Self::Error>;
}
