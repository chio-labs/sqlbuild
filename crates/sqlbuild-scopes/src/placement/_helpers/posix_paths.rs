//! The common prefix of `PurePosixPath` parts, as `_lca` joins it.

use sqlbuild_core::posix_path::main::posix_join::posix_join;
use sqlbuild_core::posix_path::main::posix_parts::posix_parts;

/// The longest common leading parts of `paths`, as `_lca` joins them.
pub(crate) fn common_prefix(paths: &[&str]) -> String {
    let split: Vec<Vec<&str>> = paths.iter().map(|path| posix_parts(path)).collect();
    let shortest: usize = split.iter().map(Vec::len).min().unwrap_or(0);
    let mut common: Vec<&str> = Vec::new();
    for position in 0..shortest {
        let component: &str = split[0][position];
        if split.iter().any(|item| item[position] != component) {
            break;
        }
        common.push(component);
    }
    posix_join(&common)
}
