//! `[skills]` project settings and skill target names.

use std::path::{Path, PathBuf};

use crate::models::ConfigValue;
use crate::toml::main::load_toml::load_toml;
use crate::workspace::_helpers::files::read_text;
use crate::workspace::constants::{
    CLAUDE_TARGET, DEFAULT_SKILL_TARGETS, GIT_MARKER, OPENCODE_TARGET, SKILL_ENTRY_FILE,
    SKILL_NAME, UTF8_BYTE_ORDER_MARK, VALID_SKILL_TARGETS,
};
use crate::workspace::errors::WorkspaceError;
use sqlbuild_core::constants::PROJECT_CONFIG_FILENAME;

/// Project skill installation preferences (`SkillSettings`).
pub(crate) struct SkillSettings {
    pub(crate) targets: Vec<String>,
    pub(crate) auto_update: bool,
    pub(crate) configured: bool,
}

fn unconfigured() -> SkillSettings {
    SkillSettings {
        targets: Vec::new(),
        auto_update: false,
        configured: false,
    }
}

/// The default targets, `agents` and `claude`.
pub(crate) fn default_targets() -> Vec<String> {
    DEFAULT_SKILL_TARGETS
        .iter()
        .map(|target| (*target).to_owned())
        .collect()
}

/// `normalize_skill_targets`: lower-cased, validated, first occurrence kept.
pub(crate) fn normalize_targets(
    targets: &[String],
    source: &str,
) -> Result<Vec<String>, WorkspaceError> {
    let mut normalized: Vec<String> = Vec::new();
    for target in targets {
        let name: String = target.trim().to_lowercase();
        if !VALID_SKILL_TARGETS.contains(&name.as_str()) {
            return Err(WorkspaceError::user(
                "C801",
                format!("{source} contains unsupported skill target '{target}'"),
                Some(&format!(
                    "supported targets are: {}",
                    VALID_SKILL_TARGETS.join(", ")
                )),
            ));
        }
        if !normalized.contains(&name) {
            normalized.push(name);
        }
    }
    Ok(normalized)
}

fn entry<'a>(map: &'a [(ConfigValue, ConfigValue)], key: &str) -> Option<&'a ConfigValue> {
    map.iter()
        .find(|(name, _)| matches!(name, ConfigValue::String(text) if text == key))
        .map(|(_, value)| value)
}

fn string_list(value: &ConfigValue) -> Option<Vec<String>> {
    let ConfigValue::List(items) = value else {
        return None;
    };
    items
        .iter()
        .map(|item| match item {
            ConfigValue::String(text) => Some(text.clone()),
            _ => None,
        })
        .collect()
}

/// `load_project_skill_settings`.
pub(crate) fn load_settings(project_dir: &Path) -> Result<SkillSettings, WorkspaceError> {
    let path: PathBuf = project_dir.join(PROJECT_CONFIG_FILENAME);
    if !path.exists() {
        return Ok(unconfigured());
    }
    let text: String = read_text(&path)?;
    let text: &str = text.strip_prefix(UTF8_BYTE_ORDER_MARK).unwrap_or(&text);
    let shown: String = path.display().to_string();
    let document: ConfigValue = load_toml(text).map_err(|error| {
        WorkspaceError::user(
            "C802",
            format!("{shown} contains invalid TOML: {}", error.message),
            None,
        )
    })?;
    let ConfigValue::Map(document) = document else {
        return Ok(unconfigured());
    };
    let Some(skills) = entry(&document, "skills") else {
        return Ok(unconfigured());
    };
    let ConfigValue::Map(skills) = skills else {
        return Err(WorkspaceError::user(
            "C803",
            format!("{shown} [skills] must be a table"),
            None,
        ));
    };
    let targets: Option<Vec<String>> = match entry(skills, "targets") {
        None => None,
        Some(value) => Some(string_list(value).ok_or_else(|| {
            WorkspaceError::user(
                "C804",
                format!("{shown} skills.targets must be a list of strings"),
                None,
            )
        })?),
    };
    let auto_update: bool = match entry(skills, "auto_update") {
        None => false,
        Some(ConfigValue::Bool(flag)) => *flag,
        Some(_) => {
            return Err(WorkspaceError::user(
                "C808",
                format!("{shown} skills.auto_update must be a boolean"),
                None,
            ));
        }
    };
    let targets: Vec<String> = match targets {
        Some(targets) => normalize_targets(&targets, "skills.targets")?,
        None => Vec::new(),
    };
    Ok(SkillSettings {
        targets: if targets.is_empty() {
            default_targets()
        } else {
            targets
        },
        auto_update,
        configured: true,
    })
}

/// `_find_git_root`: the nearest directory, from `project_dir` up, holding `.git`.
fn git_root(project_dir: &Path) -> Option<&Path> {
    project_dir
        .ancestors()
        .find(|candidate| candidate.join(GIT_MARKER).exists())
}

/// `build_install_targets`: the `SKILL.md` path of every target.
pub(crate) fn install_paths(
    project_dir: &Path,
    targets: &[String],
    home: Option<&Path>,
) -> Vec<PathBuf> {
    let local: &Path = git_root(project_dir).unwrap_or(project_dir);
    targets
        .iter()
        .map(|target| {
            let base: PathBuf = match (target.as_str(), home) {
                (OPENCODE_TARGET, Some(home)) => home.join(".config/opencode"),
                (OPENCODE_TARGET, None) => local.join(".opencode"),
                (CLAUDE_TARGET, Some(home)) => home.join(".claude"),
                (CLAUDE_TARGET, None) => local.join(".claude"),
                (_, Some(home)) => home.join(".agents"),
                (_, None) => local.join(".agents"),
            };
            base.join("skills").join(SKILL_NAME).join(SKILL_ENTRY_FILE)
        })
        .collect()
}
