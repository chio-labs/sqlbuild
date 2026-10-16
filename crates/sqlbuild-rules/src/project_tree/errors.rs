//! Why a project-relative path is not a file rules may read.

use std::path::PathBuf;

/// The reason a project path cannot be read through the project tree.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ProjectTreeFileError {
    /// The path is absolute or climbs out with `..`.
    Escapes,
    /// The path holds a NUL byte, which no file name can.
    EmbeddedNul,
    /// No regular file exists at the path inside the project.
    Missing,
    /// The file is not one of the tracked text types.
    Untracked,
    /// The path resolves through a symbolic link.
    Symlink,
    /// Testing the resolved path failed with this `errno`, or Windows error code.
    Unreadable { path: PathBuf, errno: i32 },
}

/// Why a path has no parts relative to the project or the requested directory.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum RelativePartsError<E> {
    /// Resolving the absolute path failed.
    Resolve(E),
    /// The resolved path is outside the project.
    Escapes,
    /// The path is not beneath the requested directory.
    NotBeneath,
}
