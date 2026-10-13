//! Playground template choice and the commands its summary suggests.

use std::path::{Path, PathBuf};

use crate::workspace::_helpers::files::{copy_entries, copy_tree};
use crate::workspace::constants::{
    DAGSTER_COMMAND, DAGSTER_TEMPLATE, DEFAULT_EXAMPLE, LOADER_WAFFLE_SHOP_TEMPLATE,
    ORCHESTRATED_PROJECT_DIR, ORCHESTRATED_TEMPLATES, PLAYGROUND_EXAMPLES, PROJECT_COMMANDS,
    PYTHON_NODES_COMMANDS, PYTHON_NODES_TEMPLATE, RIVERS_COMMAND, RIVERS_TEMPLATE,
    WAFFLE_SHOP_TEMPLATE,
};
use crate::workspace::errors::WorkspaceError;

/// Whether the template puts the project under `waffle_shop/` beside orchestrator files.
pub(crate) fn orchestrated(template: &str) -> bool {
    ORCHESTRATED_TEMPLATES.contains(&template)
}

/// Copy the chosen template into the new target directory.
pub(crate) fn write_template(
    root: &Path,
    target: &Path,
    template: &str,
) -> Result<(), WorkspaceError> {
    if template == PYTHON_NODES_TEMPLATE {
        return copy_tree(&root.join(PYTHON_NODES_TEMPLATE), target);
    }
    let project: &str = if template == LOADER_WAFFLE_SHOP_TEMPLATE {
        LOADER_WAFFLE_SHOP_TEMPLATE
    } else {
        WAFFLE_SHOP_TEMPLATE
    };
    let project_root: PathBuf = root.join(project);
    if !project_root.is_dir() {
        return Err(WorkspaceError::user(
            "C702",
            "packaged playground template is missing".to_owned(),
            Some("reinstall SQLBuild or report a packaging issue"),
        ));
    }
    if !orchestrated(template) {
        return copy_tree(&project_root, target);
    }
    copy_tree(&project_root, &target.join(ORCHESTRATED_PROJECT_DIR))?;
    copy_entries(&root.join(template), target)
}

/// `_suggested_commands`.
pub(crate) fn suggested_commands(template: &str, display_path: &str) -> Vec<String> {
    let project_path: String = if orchestrated(template) {
        format!("{display_path}/{ORCHESTRATED_PROJECT_DIR}")
    } else {
        display_path.to_owned()
    };
    let mut commands: Vec<String> = vec![format!("cd {project_path}")];
    let steps: &[&str] = if template == PYTHON_NODES_TEMPLATE {
        &PYTHON_NODES_COMMANDS
    } else {
        &PROJECT_COMMANDS
    };
    commands.extend(steps.iter().map(|step| (*step).to_owned()));
    if orchestrated(template) {
        commands.push("cd ..".to_owned());
    }
    if template == DAGSTER_TEMPLATE {
        commands.push(DAGSTER_COMMAND.to_owned());
    }
    if template == RIVERS_TEMPLATE {
        commands.push(RIVERS_COMMAND.to_owned());
    }
    commands
}

/// `_example_name`.
pub(crate) fn example_name(template: &str) -> &'static str {
    PLAYGROUND_EXAMPLES
        .iter()
        .find(|(name, _)| *name == template)
        .map_or(DEFAULT_EXAMPLE, |(_, label)| label)
}
