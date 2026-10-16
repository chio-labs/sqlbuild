//! `Path.resolve()`: symbolic links resolved through every existing prefix, the rest kept.

use std::io::{Error, ErrorKind};
use std::path::{Component, Path, PathBuf};

use crate::project_tree::_helpers::files::real_path;
use crate::project_tree::constants::EMBEDDED_NUL_BYTE;

/// The absolute path with each existing prefix resolved and `..` applied to what it resolved to.
pub fn resolve_project_path(path: &Path) -> std::io::Result<PathBuf> {
    if path.as_os_str().as_encoded_bytes().contains(&0) {
        return Err(Error::new(ErrorKind::InvalidInput, EMBEDDED_NUL_BYTE));
    }
    let absolute: PathBuf = if path.is_absolute() {
        path.to_path_buf()
    } else {
        std::env::current_dir()?.join(path)
    };
    let mut resolved: PathBuf = PathBuf::new();
    let mut missing: bool = false;
    for component in absolute.components() {
        match component {
            Component::ParentDir => {
                resolved.pop();
            }
            Component::CurDir => {}
            Component::Normal(part) => {
                let next: PathBuf = resolved.join(part);
                resolved = if missing {
                    next
                } else {
                    match real_path(&next) {
                        Ok(real) => real,
                        Err(_unresolved) => {
                            missing = true;
                            next
                        }
                    }
                };
            }
            Component::Prefix(_) | Component::RootDir => resolved.push(component.as_os_str()),
        }
    }
    Ok(resolved)
}
