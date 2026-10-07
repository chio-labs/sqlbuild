//! Read and load the given YAML files in parallel.

use crate::_helpers::pool::discovery_pool;
use crate::_helpers::reading::read_authored_text;
use crate::models::{FailureKind, ProjectRoot, StageFailure};
use crate::tree::models::ProjectTree;
use crate::yaml_files::_helpers::failures::yaml_failure;
use crate::yaml_files::models::YamlFileOutcome;
use rayon::iter::{IntoParallelRefIterator, ParallelIterator};
use sqlbuild_config::yaml::main::safe_load::safe_load;

/// Each file's outcome, in the order of `relative_paths`; failures are raised as `kind`.
pub fn load_yaml_files(
    root: &ProjectRoot,
    tree: &ProjectTree,
    relative_paths: &[String],
    kind: FailureKind,
) -> Result<Vec<YamlFileOutcome>, StageFailure> {
    let pool = discovery_pool().map_err(StageFailure::Internal)?;
    Ok(pool.install(|| {
        relative_paths
            .par_iter()
            .map(
                |relative_path| match read_authored_text(&tree.absolute(relative_path)) {
                    Ok(contents) => match safe_load(&contents) {
                        Ok(value) => YamlFileOutcome::Loaded { contents, value },
                        Err(error) => YamlFileOutcome::Failed(yaml_failure(
                            &root.display_path(relative_path),
                            kind,
                            error,
                        )),
                    },
                    Err(failure) => YamlFileOutcome::Unreadable(failure),
                },
            )
            .collect()
    }))
}
