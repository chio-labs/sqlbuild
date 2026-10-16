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

/// Why a tracked project file's text cannot be read.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ProjectTextError {
    /// The path names no file rules may read.
    File(ProjectTreeFileError),
    /// Opening or reading the file at `path` failed with this `errno`.
    Read { path: PathBuf, errno: i32 },
    /// The file is not valid UTF-8.
    Decode(Utf8Failure),
}

/// The first invalid UTF-8 sequence, as Python's strict decoder reports it.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Utf8Failure {
    pub byte: u8,
    pub start: usize,
    pub end: usize,
    pub reason: Utf8Reason,
}

/// The reason Python's UTF-8 decoder gives.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Utf8Reason {
    InvalidStart,
    InvalidContinuation,
    UnexpectedEnd,
}
