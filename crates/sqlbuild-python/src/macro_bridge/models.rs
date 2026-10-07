//! Python classes of the macro bridge.

use pyo3::pyclass;
use std::sync::Mutex;

/// The macro call results one compile records and replays, keyed by call class and call text.
#[pyclass(module = "sqlbuild._native", frozen)]
#[derive(Debug, Default)]
pub(crate) struct MacroCallMemo {
    pub(crate) inner: Mutex<sqlbuild_render::macro_calls::models::MacroCallMemo>,
}
