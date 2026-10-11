//! Model and column references in YAML declarations, as `yaml_edits.py` finds them.

use sqlbuild_config::errors::ConfigErrorKind;
use sqlbuild_config::models::{ComposedYaml, ComposedYamlContent, ComposedYamlNode};
use sqlbuild_config::yaml::main::compose_marks::compose_marks;

use crate::refactoring::_helpers::edits::text_edits::{path_edits, text_edit};
use crate::refactoring::_helpers::scanning::chars::{chars, find};
use crate::refactoring::_helpers::scanning::sql_sites::embedded_ref_spans;
use crate::refactoring::constants::{
    RELATIONSHIPS_AUDIT, RELATIONSHIPS_FIELD_KEY, RELATIONSHIPS_TO_KEY,
};
use crate::refactoring::errors::RefactorError;
use crate::refactoring::models::{DiscoveredFile, EditKind, TextEdit};

/// The `to` and `field` scalars of one relationships audit.
struct YamlRelationship<'a> {
    target: Option<&'a ComposedYamlNode>,
    field: Option<&'a ComposedYamlNode>,
}

/// One YAML file's text and composed nodes, or `None` where PyYAML raises a `YAMLError`.
struct ComposedFile<'a> {
    file: &'a DiscoveredFile,
    text: Vec<char>,
    document: ComposedYaml,
}

fn compose(file: &DiscoveredFile) -> Result<Option<ComposedFile<'_>>, RefactorError> {
    match compose_marks(&file.contents) {
        Ok(document) if document.root.is_some() => Ok(Some(ComposedFile {
            file,
            text: chars(&file.contents),
            document,
        })),
        Ok(_) => Ok(None),
        Err(error) if error.kind == ConfigErrorKind::Unsupported => Err(RefactorError::internal(
            format!("{}: {}", file.path, error.message),
        )),
        Err(_) => Ok(None),
    }
}

impl ComposedFile<'_> {
    fn node(&self, id: usize) -> &ComposedYamlNode {
        &self.document.nodes[id]
    }

    fn scalar_value(node: &ComposedYamlNode) -> Option<&str> {
        node.content.as_scalar()
    }

    fn raw(&self, node: &ComposedYamlNode) -> Vec<char> {
        let end = node.end.min(self.text.len());
        self.text[node.start.min(end)..end].to_vec()
    }

    /// Every scalar reached through sequence items and mapping values, in document order.
    fn scalars(&self, id: usize) -> Vec<usize> {
        match &self.node(id).content {
            ComposedYamlContent::Scalar(_) => vec![id],
            ComposedYamlContent::Sequence(items) => {
                items.iter().flat_map(|item| self.scalars(*item)).collect()
            }
            ComposedYamlContent::Mapping(entries) => entries
                .iter()
                .flat_map(|(_, value)| self.scalars(*value))
                .collect(),
        }
    }

    fn relationships(&self, id: usize) -> Vec<YamlRelationship<'_>> {
        let mut found: Vec<YamlRelationship<'_>> = Vec::new();
        match &self.node(id).content {
            ComposedYamlContent::Mapping(entries) => {
                for (key, value) in entries {
                    let is_audit = Self::scalar_value(self.node(*key)) == Some(RELATIONSHIPS_AUDIT);
                    if is_audit
                        && let ComposedYamlContent::Mapping(audit) = &self.node(*value).content
                    {
                        found.push(self.relationship(audit));
                    }
                    found.extend(self.relationships(*value));
                }
            }
            ComposedYamlContent::Sequence(items) => {
                for item in items {
                    found.extend(self.relationships(*item));
                }
            }
            ComposedYamlContent::Scalar(_) => {}
        }
        found
    }

    fn relationship(&self, entries: &[(usize, usize)]) -> YamlRelationship<'_> {
        let mut target: Option<&ComposedYamlNode> = None;
        let mut field: Option<&ComposedYamlNode> = None;
        for (key, value) in entries {
            let value_node = self.node(*value);
            if Self::scalar_value(value_node).is_none() {
                continue;
            }
            match Self::scalar_value(self.node(*key)) {
                Some(RELATIONSHIPS_TO_KEY) => target = Some(value_node),
                Some(RELATIONSHIPS_FIELD_KEY) => field = Some(value_node),
                _ => {}
            }
        }
        YamlRelationship { target, field }
    }

    fn rename_scalar(&self, node: &ComposedYamlNode, new: &str, kind: EditKind) -> TextEdit {
        let value = Self::scalar_value(node).unwrap_or_default();
        let raw: Vec<char> = chars(&self.raw(node).iter().collect::<String>().to_lowercase());
        let offset = find(&raw, &value.to_lowercase(), 0).unwrap_or(0);
        let start = node.start + offset;
        text_edit(
            &self.text,
            (start, start + value.chars().count()),
            new.to_owned(),
            kind,
        )
    }

    fn targets(&self, relationship: &YamlRelationship<'_>, model: &str) -> bool {
        let Some(target) = relationship.target else {
            return false;
        };
        Self::scalar_value(target) == Some(model)
            || !embedded_ref_spans(&self.raw(target), model).is_empty()
    }
}

/// Rename `__ref` calls in YAML strings and bare relationships targets naming a model.
pub(crate) fn yaml_model_edits(
    files: &[DiscoveredFile],
    old: &str,
    new: &str,
) -> Result<Vec<(String, TextEdit)>, RefactorError> {
    let mut edits: Vec<(String, TextEdit)> = Vec::new();
    for file in files {
        let Some(composed) = compose(file)? else {
            continue;
        };
        let root = composed.document.root.unwrap_or_default();
        let scalars: Vec<usize> = composed.scalars(root);
        let mut found: Vec<TextEdit> = Vec::new();
        for id in scalars {
            let node = composed.node(id);
            found.extend(
                embedded_ref_spans(&composed.raw(node), old)
                    .into_iter()
                    .map(|(start, end)| {
                        text_edit(
                            &composed.text,
                            (node.start + start, node.start + end),
                            new.to_owned(),
                            EditKind::Reference,
                        )
                    }),
            );
        }
        found.extend(
            composed
                .relationships(root)
                .into_iter()
                .filter_map(|relationship| relationship.target)
                .filter(|target| ComposedFile::scalar_value(target) == Some(old))
                .map(|target| composed.rename_scalar(target, new, EditKind::Reference)),
        );
        edits.extend(path_edits(&composed.file.path, found));
    }
    Ok(edits)
}

/// Rename relationships `field` values that point at a renamed column of a model.
pub(crate) fn yaml_column_edits(
    files: &[DiscoveredFile],
    model: &str,
    old: &str,
    new: &str,
) -> Result<Vec<(String, TextEdit)>, RefactorError> {
    let mut edits: Vec<(String, TextEdit)> = Vec::new();
    for file in files {
        let Some(composed) = compose(file)? else {
            continue;
        };
        let root = composed.document.root.unwrap_or_default();
        let found: Vec<TextEdit> = composed
            .relationships(root)
            .iter()
            .filter(|relationship| {
                relationship.field.is_some_and(|field| {
                    ComposedFile::scalar_value(field)
                        .unwrap_or_default()
                        .to_lowercase()
                        == old.to_lowercase()
                }) && composed.targets(relationship, model)
            })
            .filter_map(|relationship| relationship.field)
            .map(|field| composed.rename_scalar(field, new, EditKind::Column))
            .collect();
        edits.extend(path_edits(&composed.file.path, found));
    }
    Ok(edits)
}
