//! Collect the timings one compile records on this thread.

use std::rc::Rc;

use crate::compile_context::_helpers::active::replace_active;
use crate::compile_context::types::CompileTimingsHandle;

/// Run `body` with a fresh collector active on this thread, restoring the previous one after.
pub fn collect_compile_timings<T, E>(
    body: impl FnOnce(&CompileTimingsHandle) -> Result<T, E>,
) -> Result<T, E> {
    let collector: CompileTimingsHandle = Rc::default();
    let previous: Option<CompileTimingsHandle> = replace_active(Some(Rc::clone(&collector)));
    let result: Result<T, E> = body(&collector);
    let _ = replace_active(previous);
    result
}
