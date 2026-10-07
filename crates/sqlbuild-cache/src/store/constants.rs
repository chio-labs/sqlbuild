//! The native store file format.

/// The first bytes of every store file.
pub const STORE_MAGIC: &[u8; 8] = b"SQBSTORE";
/// Bumped whenever the file layout changes; older files are discarded whole.
pub const STORE_FORMAT_VERSION: u32 = 1;
/// Saves an unused entry survives while the store's environment is unchanged.
pub const RETAINED_GENERATIONS: u64 = 64;
