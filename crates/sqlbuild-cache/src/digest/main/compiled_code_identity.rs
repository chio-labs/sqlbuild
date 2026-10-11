//! The digest that changes with every installed code version and every native rebuild.

use sha2::{Digest, Sha256};

use crate::digest::_helpers::code_files::lowercase_hex;

/// SHA-256 of the installed code's identity and the native build's identity.
#[must_use]
pub fn compiled_code_identity(installed: &str, build_identity: &str) -> String {
    lowercase_hex(&Sha256::digest(
        format!("{installed}\0{build_identity}").as_bytes(),
    ))
}
