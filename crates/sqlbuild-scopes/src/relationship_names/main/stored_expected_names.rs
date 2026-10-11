//! One test file's stored expected-model names, read back from the shared scan store.

/// Every block's names when `value` is exactly a list of `block_count` lists of strings.
#[must_use]
pub fn stored_expected_names(value: &[u8], block_count: usize) -> Option<Vec<Vec<String>>> {
    let stored: Vec<Vec<String>> = match serde_json::from_slice(value) {
        Ok(stored) => stored,
        Err(_) => return None,
    };
    (stored.len() == block_count).then_some(stored)
}
