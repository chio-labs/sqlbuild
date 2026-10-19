//! Where the interpreter discovery cache lives.

use std::path::PathBuf;

use crate::host::constants::CACHE_DIRECTORY;

/// `$XDG_CACHE_HOME/sqlbuild/interpreters`, else `~/.cache/sqlbuild/interpreters`.
#[must_use]
pub fn host_cache_root() -> Option<PathBuf> {
    let absolute = |variable: &str| {
        std::env::var_os(variable)
            .map(PathBuf::from)
            .filter(|path| path.is_absolute())
    };
    let mut root: PathBuf =
        absolute("XDG_CACHE_HOME").or_else(|| absolute("HOME").map(|home| home.join(".cache")))?;
    root.extend(CACHE_DIRECTORY);
    Some(root)
}
