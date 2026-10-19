//! Decide whether the Python CLI script's interpreter can run in this process.

use std::path::{Path, PathBuf};

use crate::host::_helpers::cache::{interpreter_stamp, read_cached, write_cached};
use crate::host::_helpers::installation::locate_library;
use crate::host::_helpers::script::script_interpreter;
use crate::host::models::{HostDiscovery, LocatedHost};

/// How to start the console script at `script`, using and refreshing the cache under `cache_root`.
#[must_use]
pub fn discover_host(script: &Path, cache_root: Option<&Path>) -> HostDiscovery {
    if !cfg!(target_os = "linux") {
        return HostDiscovery::Exec(
            "running Python in the sqb process is not supported on this platform".to_owned(),
        );
    }
    let interpreter: PathBuf = match script_interpreter(script) {
        Ok(interpreter) => interpreter,
        Err(reason) => return HostDiscovery::Exec(reason),
    };
    let Some(stamp) = interpreter_stamp(&interpreter) else {
        return HostDiscovery::Exec(format!("cannot find {}", interpreter.display()));
    };
    if let Some(cached) = cache_root.and_then(|root| read_cached(root, &interpreter, &stamp)) {
        return cached;
    }
    let located: LocatedHost = locate_library(&interpreter);
    if let Some(root) = cache_root.filter(|_| located.cacheable) {
        write_cached(root, &interpreter, &stamp, &located);
    }
    located.found
}
