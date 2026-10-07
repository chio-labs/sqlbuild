//! What the project fingerprint walk skips; the same folders project reuse leaves out.

/// Folders skipped only directly below the project root.
pub const EXCLUDED_ROOT_DIRECTORIES: &[&str] = &[
    "logs",
    "target",
    "venv",
    ".cache",
    ".fensu",
    ".hg",
    ".idea",
    ".mypy_cache",
    ".nox",
    ".pytest_cache",
    ".ruff_cache",
    ".sqlbuild",
    ".svn",
    ".tox",
    ".venv",
    ".vscode",
];

/// Folders skipped at any depth.
pub const EXCLUDED_DIRECTORIES: &[&str] = &[".git", "__pycache__"];

/// Files that count only by presence because every build rewrites them.
pub const PRESENCE_ONLY_FILE_SUFFIXES: &[&str] = &[".duckdb", ".duckdb.wal"];

/// Digest tag of a file whose bytes count.
pub const CONTENT_TAG: &[u8] = b"content";
/// Digest tag of a file that counts only by presence.
pub const PRESENCE_TAG: &[u8] = b"presence";
