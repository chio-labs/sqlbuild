//! Which `*.py` paths below a root Python module discovery keeps.

use crate::declaration_files::constants::PRIVATE_PREFIX;
use sqlbuild_core::constants::PYTHON_INIT_MODULE_STEM as INIT_MODULE_STEM;

/// Whether `relative_path` below `root` is a listed module: never `__init__`, and public if asked.
pub(crate) fn is_listed_module(relative_path: &str, root: &str, public_only: bool) -> bool {
    let below: &str = relative_path
        .strip_prefix(root)
        .map_or(relative_path, |rest| rest.trim_start_matches('/'));
    let name: &str = below.rsplit('/').next().unwrap_or(below);
    let stem: &str = name.rsplit_once('.').map_or(name, |(stem, _)| stem);
    stem != INIT_MODULE_STEM && !(public_only && has_private_part(below))
}

fn has_private_part(path: &str) -> bool {
    path.split('/').any(|part| part.starts_with(PRIVATE_PREFIX))
}
