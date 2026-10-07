//! Read and load the given YAML files in parallel, deferring each file Python must load.

use crate::_helpers::pool::discovery_pool;
use crate::_helpers::reading::read_authored_text;
use crate::models::StageDeferral;
use crate::tree::models::ProjectTree;
use crate::yaml_files::models::YamlFileOutcome;
use rayon::iter::{IntoParallelRefIterator, ParallelIterator};
use sqlbuild_config::yaml::main::safe_load::safe_load;

/// Each file's outcome, in the order of `relative_paths`.
pub fn load_yaml_files(
    tree: &ProjectTree,
    relative_paths: &[String],
) -> Result<Vec<YamlFileOutcome>, StageDeferral> {
    let pool = discovery_pool().map_err(|reason| StageDeferral { reason })?;
    Ok(pool.install(|| {
        relative_paths
            .par_iter()
            .map(
                |relative_path| match read_authored_text(&tree.absolute(relative_path)) {
                    Ok(contents) => match safe_load(&contents) {
                        Ok(value) => YamlFileOutcome::Loaded { contents, value },
                        Err(_deferred) => YamlFileOutcome::LoadInPython { contents },
                    },
                    Err(_unreadable) => YamlFileOutcome::Unreadable,
                },
            )
            .collect()
    }))
}
