//! Replace a scenario run directory with its runtime SQL artifacts.

use std::fs;
use std::io;
use std::path::{Path, PathBuf};

use crate::scenario_command::models::RuntimeArtifact;
use crate::text::main::python_isspace::python_isspace;

/// Remove `root`, then write each artifact's SQL without trailing whitespace and with one newline.
pub fn write_runtime_artifacts(root: &Path, artifacts: &[RuntimeArtifact]) -> io::Result<()> {
    if root.exists() {
        fs::remove_dir_all(root)?;
    }
    for artifact in artifacts {
        let path: PathBuf = root.join(&artifact.relative_path);
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)?;
        }
        fs::write(
            &path,
            format!("{}\n", artifact.sql.trim_end_matches(python_isspace)),
        )?;
    }
    Ok(())
}
