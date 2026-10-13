//! The capture document, written as shared nodes followed by its root.

use sqlbuild_core::json::errors::JsonEmitError;
use sqlbuild_core::json::main::dumps::dumps;
use sqlbuild_core::json::models::JsonValue;

use crate::stage_capture::_helpers::dialect::capture_dialect;
use crate::stage_capture::constants::{ROOT_KEY, SHARED_NODES_KEY};

/// One capture document: each shared node and then the root, each on its own line.
#[derive(Debug, Default)]
pub struct CaptureDocument {
    shared: bool,
}

impl CaptureDocument {
    /// The text that appends one shared node, given as compact JSON.
    pub fn shared_chunk(&mut self, digest: &str, text: &str) -> String {
        let prefix: String = if self.shared {
            ",\n".to_owned()
        } else {
            format!("{{\"{SHARED_NODES_KEY}\": {{\n")
        };
        self.shared = true;
        format!("{prefix}\"{digest}\": {text}")
    }

    /// The text that writes the root and closes the document.
    pub fn final_chunk(&self, root: &JsonValue) -> Result<String, JsonEmitError> {
        if !self.shared {
            return Ok(dumps(root, &capture_dialect(Some(1), (",", ": ")))? + "\n");
        }
        let compact: String = dumps(root, &capture_dialect(None, (",", ":")))?;
        Ok(format!("\n}},\n\"{ROOT_KEY}\": {compact}\n}}\n"))
    }
}
