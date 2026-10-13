//! The key metadata rows are sorted by.

/// A row's path and digest code points, the key Python sorts rows by.
pub type RowKey = (Vec<u32>, Vec<u32>);
