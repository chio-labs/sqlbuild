//! The digest that changes with every released or locally edited version of the installed code.

use std::path::Path;

use sha2::{Digest, Sha256};

use crate::digest::_helpers::code_files::{lowercase_hex, source_file_stats};

/// SHA-256 of each fact `\0`-terminated, then each source file below an editable `package_root`.
#[must_use]
pub fn installed_code_identity(facts: &[String], package_root: Option<&Path>) -> String {
    let mut hasher: Sha256 = Sha256::new();
    for fact in facts {
        hasher.update(fact.as_bytes());
        hasher.update(b"\0");
    }
    if let Some(root) = package_root {
        for (relative_path, size, modified) in source_file_stats(root) {
            hasher.update(format!("{relative_path}\0{size}\0{modified}\0").as_bytes());
        }
    }
    lowercase_hex(&hasher.finalize())
}
