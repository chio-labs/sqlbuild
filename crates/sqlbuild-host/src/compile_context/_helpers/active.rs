//! The thread's active collector slot.

use std::cell::RefCell;

use crate::compile_context::types::CompileTimingsHandle;

thread_local! {
    static ACTIVE: RefCell<Option<CompileTimingsHandle>> = const { RefCell::new(None) };
}

/// Make `collector` the thread's active collector; return the one it replaces.
pub(crate) fn replace_active(
    collector: Option<CompileTimingsHandle>,
) -> Option<CompileTimingsHandle> {
    ACTIVE.with(|active| active.replace(collector))
}

/// The thread's active collector, if a compile is collecting.
pub(crate) fn active() -> Option<CompileTimingsHandle> {
    ACTIVE.with(|active| active.borrow().clone())
}
