//! Whether a Python-node status is a failure.

use crate::build_command::constants::PYTHON_NODE_FAILED;

/// Only the `failed` status fails the build.
#[must_use]
pub fn python_node_failed(status: &str) -> bool {
    status == PYTHON_NODE_FAILED
}
