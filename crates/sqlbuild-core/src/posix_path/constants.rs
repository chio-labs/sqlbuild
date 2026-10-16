//! `PurePosixPath` separators and anchors.

pub(crate) const SEPARATOR: char = '/';
pub(crate) const ROOT: &str = "/";
/// POSIX keeps exactly two leading slashes as their own root.
pub(crate) const DOUBLE_ROOT: &str = "//";
pub(crate) const CURRENT: &str = ".";
pub(crate) const SUFFIX_MARK: char = '.';
