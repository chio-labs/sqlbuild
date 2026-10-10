//! Authored model references and unrewritable ones, as `model_references.py` finds them.

use crate::refactoring::_helpers::edits::header_edits::{
    model_name_header_edits, schema_model_name_edits,
};
use crate::refactoring::_helpers::edits::text_edits::{
    identifier_sites, manual_at, path_edits, text_edit,
};
use crate::refactoring::_helpers::files::project_files::ProjectSqlFile;
use crate::refactoring::_helpers::scanning::chars::{chars, slice};
use crate::refactoring::_helpers::scanning::scan_context::ScanContext;
use crate::refactoring::_helpers::scanning::sql_sites::{
    ResourceSite, authored_offset, model_body, resource_sites,
};
use crate::refactoring::constants::{
    EXPECTED_FIXTURE_PREFIX, MODEL_RESOURCE_TYPE, REF_FIXTURE_PREFIX, REF_KIND,
};
use crate::refactoring::errors::RefactorError;
use crate::refactoring::models::{EditKind, ManualLocation, ModelFacts, SqlFileRole, TextEdit};

fn ref_sites(text: &[char], name: &str, context: &ScanContext) -> Vec<ResourceSite> {
    resource_sites(text, context)
        .into_iter()
        .filter(|site| site.kind == REF_KIND && site.name == name)
        .collect()
}

/// Rewrite `__ref`, fixture CTE names, and header references to a renamed model.
pub(crate) fn model_reference_edits(
    files: &[ProjectSqlFile],
    names: (&str, &str),
    context: &ScanContext,
) -> Result<Vec<(String, TextEdit)>, RefactorError> {
    let (old, new) = names;
    let mut edits: Vec<(String, TextEdit)> = Vec::new();
    for item in files {
        edits.extend(path_edits(&item.path, ref_edits(item, names, context)));
        if matches!(item.role, SqlFileRole::Test | SqlFileRole::Scenario) {
            edits.extend(path_edits(&item.path, fixture_edits(item, names)));
        }
        if item.role == SqlFileRole::Model {
            edits.extend(path_edits(
                &item.path,
                model_name_header_edits(&item.contents, &item.text, old, new)?,
            ));
        }
        if item.role == SqlFileRole::Schema {
            edits.extend(path_edits(
                &item.path,
                schema_model_name_edits(&item.contents, &item.text, names, context.python)?,
            ));
        }
    }
    Ok(edits)
}

fn ref_edits(item: &ProjectSqlFile, names: (&str, &str), context: &ScanContext) -> Vec<TextEdit> {
    let (old, new) = names;
    let text = &item.text;
    ref_sites(text, old, context)
        .into_iter()
        .map(|site| {
            let after = format!(
                "{}{new}{}",
                slice(text, site.start, site.name_start),
                slice(text, site.name_end, site.end)
            );
            text_edit(
                text,
                (site.name_start, site.name_end),
                new.to_owned(),
                EditKind::Reference,
            )
            .with_display(Some(slice(text, site.start, site.end)), Some(after))
        })
        .collect()
}

fn fixture_edits(item: &ProjectSqlFile, names: (&str, &str)) -> Vec<TextEdit> {
    let (old, new) = names;
    let fixture_names: [(String, String); 2] = [
        (
            format!("{REF_FIXTURE_PREFIX}{old}"),
            format!("{REF_FIXTURE_PREFIX}{new}"),
        ),
        (
            format!("{EXPECTED_FIXTURE_PREFIX}{old}"),
            format!("{EXPECTED_FIXTURE_PREFIX}{new}"),
        ),
    ];
    let searched: Vec<String> = fixture_names.iter().map(|(name, _)| name.clone()).collect();
    identifier_sites(&item.text, &searched)
        .into_iter()
        .filter_map(|(start, end, name)| {
            let replacement = fixture_replacement(&fixture_names, &name)?;
            Some(text_edit(
                &item.text,
                (start, end),
                replacement,
                EditKind::Fixture,
            ))
        })
        .collect()
}

fn fixture_replacement(fixture_names: &[(String, String)], name: &str) -> Option<String> {
    fixture_names
        .iter()
        .find(|(item, _)| item == name)
        .map(|(_, replacement)| replacement.clone())
}

fn depends_on(model: &ModelFacts, name: &str) -> bool {
    model
        .deps
        .iter()
        .any(|dep| dep.resource_type == MODEL_RESOURCE_TYPE && dep.name == name)
}

/// `__ref` calls to the model that macros produce, which no edit can reach.
pub(crate) fn macro_reference_locations(
    models: &[ModelFacts],
    files: &[ProjectSqlFile],
    old: &str,
    context: &ScanContext,
) -> Vec<ManualLocation> {
    let mut locations: Vec<ManualLocation> = Vec::new();
    for model in models {
        let Some(file) = files.iter().find(|file| file.path == model.path) else {
            continue;
        };
        if !depends_on(model, old) {
            continue;
        }
        locations.extend(generated_references(model, &file.text, old, context));
    }
    locations
}

fn generated_references(
    model: &ModelFacts,
    text: &[char],
    old: &str,
    context: &ScanContext,
) -> Vec<ManualLocation> {
    let compiled_sites = ref_sites(&chars(&model.query_sql), old, context);
    let authored_sites = ref_sites(&chars(&model.authored_query_sql), old, context);
    if compiled_sites.len() <= authored_sites.len() {
        return Vec::new();
    }
    let Some(body) = model_body(model, text) else {
        return vec![manual_at(
            &model.path,
            text,
            None,
            format!("reference to {old} produced by a macro"),
        )];
    };
    compiled_sites
        .iter()
        .map(|site| authored_offset(&body, site.start))
        .filter(|(_, generated)| *generated)
        .map(|(offset, _)| {
            manual_at(
                &model.path,
                text,
                Some(offset),
                format!(
                    "reference to {old} produced by a macro; pass the model to the macro as an argument"
                ),
            )
        })
        .collect()
}
