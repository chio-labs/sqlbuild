//! Directories the project tree skips and the file types rules may read.

/// Top-level directories that are tooling output or environments, never project sources.
pub(crate) const EXCLUDED_ROOTS: [&str; 5] = [".git", ".venv", "logs", "target", "venv"];
/// The lowercase suffixes of the text files rules may read, sorted.
pub(crate) const TRACKED_TEXT_SUFFIXES: [&str; 5] = [".py", ".sql", ".toml", ".yaml", ".yml"];
/// The leading byte of a hidden directory name.
pub(crate) const HIDDEN_PREFIX: u8 = b'.';
/// `errno` values `pathlib` treats as a missing file when it tests `is_file()`.
#[cfg(target_os = "macos")]
pub(crate) const MISSING_FILE_ERRORS: [i32; 4] = [2, 20, 9, 62];
/// `errno` values `pathlib` treats as a missing file when it tests `is_file()`.
#[cfg(all(unix, not(target_os = "macos")))]
pub(crate) const MISSING_FILE_ERRORS: [i32; 4] = [2, 20, 9, 40];
/// Windows error codes `pathlib` treats as a missing file: those mapping to its ignored `errno`s.
#[cfg(not(unix))]
pub(crate) const MISSING_FILE_ERRORS: [i32; 15] = [
    2, 3, 15, 18, 53, 67, 161, 206, 6, 114, 130, 267, 21, 123, 1921,
];
/// The separator `as_posix()` spells and the project walk joins listed paths with.
pub(crate) const POSIX_SEPARATOR: &str = "/";
pub(crate) const POSIX_SEPARATOR_BYTE: u8 = b'/';
/// `str()` of a path with no anchor and no components.
pub(crate) const CURRENT: &str = ".";
pub(crate) const PARENT: &str = "..";
/// Private-use characters standing for undecodable path bytes or unpaired surrogates.
pub(crate) const ESCAPED_BASE: u32 = 0xF_0000;
/// The `ValueError` text `os.fspath` paths raise for a NUL byte.
pub(crate) const EMBEDDED_NUL_BYTE: &str = "embedded null byte";
pub(crate) const LINE_FEED: &str = "\n";
/// Bytes that can never start a UTF-8 sequence.
pub(crate) const UTF8_INVALID_START: [std::ops::RangeInclusive<u8>; 2] = [0x80..=0xC1, 0xF5..=0xFF];
