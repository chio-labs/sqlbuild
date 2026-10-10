//! Authored project files and SQL bodies a refactoring reads and edits, as `project_files.py`
//! collects them.

use std::collections::BTreeMap;

use sqlbuild_core::text::main::python_strip::python_strip;

use crate::refactoring::_helpers::chars::{chars, find};
use crate::refactoring::models::{DiscoveredFile, RefactorFacts, SqlFileRole};

/// One authored SQL file, the role discovery gave it, and its code points.
#[derive(Clone, Debug)]
pub(crate) struct ProjectSqlFile {
    pub(crate) path: String,
    pub(crate) contents: String,
    pub(crate) text: Vec<char>,
    pub(crate) role: SqlFileRole,
}

/// One SQL body inside an authored non-model file.
#[derive(Clone, Debug)]
pub(crate) struct AuthoredBody {
    pub(crate) path: String,
    pub(crate) role: SqlFileRole,
    pub(crate) text: Vec<char>,
    pub(crate) contents: Vec<char>,
    pub(crate) start: usize,
    pub(crate) body: String,
}

/// Every discovered SQL file with its authored contents, the first file of a path winning,
/// sorted by path.
pub(crate) fn project_sql_files(facts: &RefactorFacts) -> Vec<ProjectSqlFile> {
    let mut files: BTreeMap<String, ProjectSqlFile> = BTreeMap::new();
    let models = facts.model_files.iter().map(|file| {
        (
            SqlFileRole::Model,
            file.path.as_str(),
            file.contents.as_str(),
        )
    });
    let authored = facts
        .authored_files
        .iter()
        .map(|file| (file.role, file.path.as_str(), file.contents.as_str()));
    for (role, path, contents) in models.chain(authored) {
        files
            .entry(path.to_owned())
            .or_insert_with(|| ProjectSqlFile {
                path: path.to_owned(),
                contents: contents.to_owned(),
                text: chars(contents),
                role,
            });
    }
    files.into_values().collect()
}

/// Every source and seed YAML declaration file, the last contents of a path winning, by path.
pub(crate) fn yaml_files(facts: &RefactorFacts) -> Vec<DiscoveredFile> {
    let mut files: BTreeMap<String, String> = BTreeMap::new();
    for file in &facts.yaml_files {
        files.insert(file.path.clone(), file.contents.clone());
    }
    files
        .into_iter()
        .map(|(path, contents)| DiscoveredFile { path, contents })
        .collect()
}

/// Every non-model SQL body located in its file, in file order.
pub(crate) fn authored_bodies(facts: &RefactorFacts) -> Vec<AuthoredBody> {
    let mut bodies: Vec<AuthoredBody> = Vec::new();
    for file in &facts.authored_files {
        let contents = chars(&file.contents);
        let mut cursor = 0;
        for body in &file.texts {
            if python_strip(body).is_empty() {
                continue;
            }
            let Some(start) = find(&contents, body, cursor) else {
                continue;
            };
            let text = chars(body);
            cursor = start + text.len();
            bodies.push(AuthoredBody {
                path: file.path.clone(),
                role: file.role,
                text,
                contents: contents.clone(),
                start,
                body: body.clone(),
            });
        }
    }
    bodies
}
