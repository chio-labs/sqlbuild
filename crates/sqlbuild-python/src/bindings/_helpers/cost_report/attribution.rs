//! How far the running command attributed warehouse cost, for the invocation's terminal event.

use std::cell::RefCell;

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult};

thread_local! {
    /// Per thread, since an invocation finalizes cost and reports on the thread that runs it.
    static COST_STATUS: RefCell<Option<String>> = const { RefCell::new(None) };
}

/// Record the cost status of the latest finalization; a later one replaces it, so a run that stops before collecting keeps `pending`.
pub(crate) fn report_cost_status(status: &Bound<'_, PyAny>) -> PyResult<()> {
    let status: String = status.str()?.to_string();
    COST_STATUS.with(|slot| *slot.borrow_mut() = Some(status));
    Ok(())
}

/// The cost status the command reported, cleared so the next invocation starts without one.
pub(crate) fn take_cost_status() -> Option<String> {
    COST_STATUS.with(|slot| slot.borrow_mut().take())
}
