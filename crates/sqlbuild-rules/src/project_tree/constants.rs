//! Directories the project tree skips and the file types rules may read.

/// Top-level directories that are tooling output or environments, never project sources.
pub(crate) const EXCLUDED_ROOTS: [&str; 5] = [".git", ".venv", "logs", "target", "venv"];
/// The lowercase suffixes of the text files rules may read, sorted.
pub(crate) const TRACKED_TEXT_SUFFIXES: [&str; 5] = [".py", ".sql", ".toml", ".yaml", ".yml"];
/// The leading byte of a hidden directory name.
pub(crate) const HIDDEN_PREFIX: u8 = b'.';
/// `errno` values `pathlib` treats as a missing file when it tests `is_file()`.
#[cfg(target_os = "macos")]
pub(crate) const MISSING_FILE_ERRNOS: [i32; 4] = [2, 20, 9, 62];
#[cfg(not(target_os = "macos"))]
pub(crate) const MISSING_FILE_ERRNOS: [i32; 4] = [2, 20, 9, 40];
pub(crate) const SEPARATOR: u8 = b'/';
pub(crate) const ROOT: &[u8] = b"/";
/// POSIX keeps exactly two leading slashes as their own root.
pub(crate) const DOUBLE_ROOT: &[u8] = b"//";
pub(crate) const DESCENDANT_SEPARATOR: &[u8] = b"/";
pub(crate) const CURRENT: &[u8] = b".";
pub(crate) const PARENT: &[u8] = b"..";
/// Private-use characters standing for undecodable path bytes, one per byte value.
pub(crate) const ESCAPED_BYTE_BASE: u32 = 0xF_0000;
