//! The runtime section of `sqb debug`.

use crate::debug_report::models::{DebugLine, DebugRuntime};

/// The SQLBuild version, interpreter and platform lines.
#[must_use]
pub fn debug_runtime_lines(runtime: &DebugRuntime) -> Vec<DebugLine> {
    vec![
        DebugLine::plain(
            "sqlbuild version",
            runtime.sqlbuild_version.as_deref().unwrap_or("unknown"),
        ),
        DebugLine::plain("python version", &runtime.python_version),
        DebugLine::plain("python path", &runtime.python_path),
        DebugLine::plain("os info", &runtime.os_info),
    ]
}
