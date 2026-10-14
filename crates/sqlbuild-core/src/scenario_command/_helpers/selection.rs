//! One scenario selector matched against scenario names, files and folders.

use std::path::{Path, PathBuf};

use crate::scenario_command::_helpers::paths::{has_sql_suffix, is_under, normalized};
use crate::scenario_command::constants::{
    GRAPH_SELECTOR_EXPANSION_MARKER, GRAPH_SELECTOR_PATH_MARKER, SCENARIO_ROOT,
    UNKNOWN_SELECTOR_CODE, UNSUPPORTED_GRAPH_SELECTOR_CODE,
};
use crate::scenario_command::errors::ScenarioCommandError;
use crate::scenario_command::models::ScenarioFile;

/// The scenario's paths as selectors compare them: absolute, project-relative and root-relative.
pub(crate) struct ScenarioPaths {
    file_path: PathBuf,
    relative_path: PathBuf,
    root_relative_path: PathBuf,
}

impl ScenarioPaths {
    pub(crate) fn of(scenario: &ScenarioFile) -> Self {
        let relative_path: PathBuf = normalized(&scenario.relative_path);
        let root: PathBuf = SCENARIO_ROOT.iter().collect();
        let root_relative_path: PathBuf = relative_path
            .strip_prefix(&root)
            .map_or_else(|_| relative_path.clone(), Path::to_path_buf);
        Self {
            file_path: normalized(&scenario.file_path),
            relative_path,
            root_relative_path,
        }
    }
}

/// Reject graph expansion and path operators, which scenarios do not support.
fn validate_selector(selector: &str) -> Result<(), ScenarioCommandError> {
    if selector.starts_with(GRAPH_SELECTOR_EXPANSION_MARKER)
        || selector.ends_with(GRAPH_SELECTOR_EXPANSION_MARKER)
        || selector.contains(GRAPH_SELECTOR_PATH_MARKER)
    {
        return Err(ScenarioCommandError {
            code: UNSUPPORTED_GRAPH_SELECTOR_CODE,
            message: format!(
                "Scenario selector '{selector}' uses graph operators, which are not supported"
            ),
            help: Some(
                "Use scenario names, scenario file paths, folders, --select-file, and --exclude. \
                 Graph expansion operators such as '+model', 'model+', and 'a~b' are only \
                 supported by graph resource commands."
                    .to_owned(),
            ),
        });
    }
    Ok(())
}

/// Whether a name-less selector path names the scenario's file or one of its folders.
fn matches(paths: &ScenarioPaths, selector_path: &Path, project_dir: &Path) -> bool {
    let project_selector: PathBuf = normalized(&project_dir.join(selector_path));
    if has_sql_suffix(selector_path) {
        return paths.file_path == project_selector
            || [
                &paths.file_path,
                &paths.relative_path,
                &paths.root_relative_path,
            ]
            .contains(&&selector_path.to_path_buf());
    }
    is_under(&paths.file_path, selector_path)
        || is_under(&paths.file_path, &project_selector)
        || is_under(&paths.relative_path, selector_path)
        || is_under(&paths.root_relative_path, selector_path)
}

/// Indices of the scenarios one selector names, in project order.
pub(crate) fn selector_matches(
    scenarios: &[ScenarioFile],
    paths: &[ScenarioPaths],
    (selector, project_dir): (&str, &Path),
) -> Result<Vec<usize>, ScenarioCommandError> {
    validate_selector(selector)?;
    let selector_path: PathBuf = normalized(Path::new(selector));
    let found: Vec<usize> = scenarios
        .iter()
        .zip(paths)
        .enumerate()
        .filter(|(_, (scenario, scenario_paths))| {
            scenario.name == selector || matches(scenario_paths, &selector_path, project_dir)
        })
        .map(|(index, _)| index)
        .collect();
    if found.is_empty() {
        return Err(ScenarioCommandError {
            code: UNKNOWN_SELECTOR_CODE,
            message: format!("Unknown scenario selector '{selector}'"),
            help: None,
        });
    }
    Ok(found)
}
