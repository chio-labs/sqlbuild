//! The project image a full or delta compile stores beside its reuse slot.

use std::collections::{BTreeMap, BTreeSet};

use serde::{Deserialize, Serialize};
use sqlbuild_analysis::assembly::analysis_session::models::RelationTables;
use sqlbuild_analysis::assembly::analysis_session::types::Shapes;
use sqlbuild_cache::project_reuse::models::ImageSections;
use sqlbuild_rules::models::{EvaluateRequest, RetainedRows};

use crate::bindings::_helpers::compile_delta::context::{
    CapturedDiagnostic, CapturedModel, CapturedTest, ImageCapture, ModelShape,
};
use crate::bindings::_helpers::compile_delta::header_keys::HeaderKeys;

/// Changes whenever the image's meaning changes, so an older image is never read.
const IMAGE_FORMAT: &str = "sqlbuild-project-image-v3";
const GATE_SECTION: &str = "gate";
const FACTS_SECTION: &str = "facts";
const RULES_SECTION: &str = "rules";
const RULE_DIGESTS_SECTION: &str = "rule-digests";

/// Everything a delta compile reads of the compile it patches.
#[derive(Clone, Debug, Default)]
pub(crate) struct ProjectImage {
    pub(crate) format: String,
    pub(crate) json_output: bool,
    pub(crate) models: Vec<CapturedModel>,
    pub(crate) usages: BTreeMap<String, String>,
    pub(crate) tests: Vec<CapturedTest>,
    pub(crate) relations: ImageRelations,
    pub(crate) fact_digests: Vec<(Vec<String>, String)>,
    pub(crate) model_subjects: Option<Vec<(String, String, Option<String>)>>,
    pub(crate) diagnostics: Vec<CapturedDiagnostic>,
    pub(crate) text_models: Option<Vec<(String, bool, i64)>>,
    pub(crate) environment_names: Vec<String>,
    pub(crate) model_shapes: Vec<ModelShape>,
    pub(crate) lint_model_keys: Option<Vec<(String, String)>>,
    pub(crate) lint_file_keys: Option<Vec<(String, Option<String>)>>,
    pub(crate) header_keys: BTreeMap<String, HeaderKeys>,
    pub(crate) rules: Option<RetainedRows>,
}

/// The analysis session's final relation facts, as stored.
#[derive(Clone, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
pub(crate) struct ImageRelations {
    pub(crate) types: Shapes,
    pub(crate) nullability: Shapes,
    pub(crate) complete: Shapes,
    pub(crate) schemas: Shapes,
    pub(crate) dependency_ordered: bool,
    pub(crate) cyclic: bool,
    pub(crate) legacy_models: Vec<String>,
}

impl From<RelationTables> for ImageRelations {
    fn from(tables: RelationTables) -> Self {
        Self {
            types: tables.types,
            nullability: tables.nullability,
            complete: tables.complete,
            schemas: tables.schemas,
            dependency_ordered: tables.dependency_ordered,
            cyclic: tables.cyclic,
            legacy_models: tables.legacy_models,
        }
    }
}

impl From<ImageRelations> for RelationTables {
    fn from(relations: ImageRelations) -> Self {
        Self {
            types: relations.types,
            nullability: relations.nullability,
            complete: relations.complete,
            schemas: relations.schemas,
            dependency_ordered: relations.dependency_ordered,
            cyclic: relations.cyclic,
            legacy_models: relations.legacy_models,
        }
    }
}

/// The prefix the keys of fields a rules request serializes but never reads back share;
/// evaluation derives them again.
const DERIVED_FIELD_PREFIX: &str = ",\"empty_input_only";
const DERIVED_FIELDS: [&str; 2] = ["_test_count\":", "\":"];

/// `json` without the derived fields, each a bare number or boolean after its key.
///
/// Compact JSON escapes every quote inside strings, so these keys only match as keys.
fn without_derived_fields(json: Vec<u8>) -> Vec<u8> {
    let Ok(text) = std::str::from_utf8(&json) else {
        return json;
    };
    let mut kept: Vec<u8> = Vec::with_capacity(json.len());
    let mut copied: usize = 0;
    for (start, _) in text.match_indices(DERIVED_FIELD_PREFIX) {
        if start < copied {
            continue;
        }
        let rest: &str = &text[start + DERIVED_FIELD_PREFIX.len()..];
        let Some(field) = DERIVED_FIELDS
            .iter()
            .find(|field| rest.starts_with(**field))
        else {
            continue;
        };
        let value: &str = &rest[field.len()..];
        let length: usize = value.find([',', '}']).unwrap_or(value.len());
        kept.extend_from_slice(&json[copied..start]);
        copied = start + DERIVED_FIELD_PREFIX.len() + field.len() + length;
    }
    kept.extend_from_slice(&json[copied..]);
    kept
}

/// Rows of `table` that differ from the same relation's `types` row; `None` where equal.
fn differing(table: &Shapes, types: &Shapes) -> Vec<(String, Option<Vec<(String, String)>>)> {
    let types: std::collections::HashMap<&str, &Vec<(String, String)>> = types
        .iter()
        .map(|(name, shape)| (name.as_str(), shape))
        .collect();
    table
        .iter()
        .map(|(name, shape)| {
            let same: bool = types
                .get(name.as_str())
                .is_some_and(|typed| *typed == shape);
            (name.clone(), (!same).then(|| shape.clone()))
        })
        .collect()
}

/// `differing`'s rows restored against `types`.
fn restored(rows: Vec<(String, Option<Vec<(String, String)>>)>, types: &Shapes) -> Option<Shapes> {
    let types: std::collections::HashMap<&str, &Vec<(String, String)>> = types
        .iter()
        .map(|(name, shape)| (name.as_str(), shape))
        .collect();
    rows.into_iter()
        .map(|(name, shape)| {
            let shape: Vec<(String, String)> = match shape {
                Some(shape) => shape,
                None => (*types.get(name.as_str())?).clone(),
            };
            Some((name, shape))
        })
        .collect()
}

/// A shape table as stored: `None` where a relation's row equals its `types` row.
type StoredShapes = Vec<(String, Option<Vec<(String, String)>>)>;

/// What a delta compile reads first to decide, cheaply, whether it can patch the image.
#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub(crate) struct ImageGate {
    pub(crate) format: String,
    pub(crate) json_output: bool,
    /// Whether the stored compile reported any error diagnostic.
    pub(crate) has_errors: bool,
    /// Whether custom rules recorded which models they select.
    pub(crate) has_model_subjects: bool,
    pub(crate) models: Vec<CapturedModel>,
    pub(crate) tests: Vec<CapturedTest>,
    pub(crate) fact_digests: Vec<(Vec<String>, String)>,
    pub(crate) header_keys: BTreeMap<String, HeaderKeys>,
}

/// The rest of the image's facts as stored; shapes equal to a relation's types are stored once.
#[derive(Serialize, Deserialize)]
struct StoredFacts {
    usages: BTreeMap<String, String>,
    types: Shapes,
    nullability: Shapes,
    complete: StoredShapes,
    schemas: StoredShapes,
    dependency_ordered: bool,
    cyclic: bool,
    legacy_models: Vec<String>,
    model_subjects: Option<Vec<(String, String, Option<String>)>>,
    diagnostics: Vec<CapturedDiagnostic>,
    text_models: Option<Vec<(String, bool, i64)>>,
    environment_names: Vec<String>,
    model_shapes: StoredShapes,
    lint_model_keys: Option<Vec<(String, String)>>,
    lint_file_keys: Option<Vec<(String, Option<String>)>>,
}

fn section<'a>(sections: &'a ImageSections, name: &str) -> Option<&'a [u8]> {
    sections
        .iter()
        .find(|(section, _)| section == name)
        .map(|(_, bytes)| bytes.as_slice())
}

fn json<T: Serialize>(value: &T) -> Result<Vec<u8>, String> {
    serde_json::to_vec(value).map_err(|error| error.to_string())
}

impl ImageGate {
    /// The gate stored in `sections`, or `None` when it is unreadable or of another format.
    pub(crate) fn decode(sections: &ImageSections) -> Option<Self> {
        let gate: Self = serde_json::from_slice(section(sections, GATE_SECTION)?).ok()?;
        (gate.format == IMAGE_FORMAT).then_some(gate)
    }
}

impl ProjectImage {
    /// The image of a finished compile's capture, or why it cannot be a delta base.
    pub(crate) fn from_capture(capture: ImageCapture, json_output: bool) -> Result<Self, String> {
        if let Some(reason) = capture.unsupported {
            return Err(reason);
        }
        if capture.stdlib_json {
            return Err("the report fell back to the standard library serializer".to_owned());
        }
        let Some(relations) = capture.relations else {
            return Err("no model analysis session ran".to_owned());
        };
        if !json_output && capture.text_models.is_none() {
            return Err("no text report was rendered".to_owned());
        }
        let Some(model_shapes) = capture.model_shapes else {
            return Err("no semantic shapes were published".to_owned());
        };
        let mut environment_names: Vec<String> = capture.environment_names;
        environment_names.sort();
        environment_names.dedup();
        Ok(Self {
            format: IMAGE_FORMAT.to_owned(),
            json_output,
            models: capture.models,
            usages: capture.usages,
            tests: capture.test_chains,
            relations: relations.into(),
            fact_digests: capture.fact_digests.into_iter().collect(),
            model_subjects: capture.model_subjects,
            diagnostics: capture.diagnostics,
            text_models: capture.text_models,
            environment_names,
            model_shapes,
            lint_model_keys: capture.lint_model_keys,
            lint_file_keys: capture.lint_file_keys,
            header_keys: capture.header_keys,
            rules: capture.rules.map(|rules| rules.retained),
        })
    }

    /// The image as the sections of its file.
    pub(crate) fn encode(self) -> Result<ImageSections, String> {
        let gate: ImageGate = ImageGate {
            format: self.format,
            json_output: self.json_output,
            has_errors: self.diagnostics.iter().any(|diagnostic| diagnostic.error),
            has_model_subjects: self.model_subjects.is_some(),
            models: self.models,
            tests: self.tests,
            fact_digests: self.fact_digests,
            header_keys: self.header_keys,
        };
        let relations: ImageRelations = self.relations;
        let types: &Shapes = &relations.types;
        let facts: StoredFacts = StoredFacts {
            usages: self.usages,
            complete: differing(&relations.complete, types),
            schemas: differing(&relations.schemas, types),
            model_shapes: differing(&self.model_shapes, types),
            types: relations.types,
            nullability: relations.nullability,
            dependency_ordered: relations.dependency_ordered,
            cyclic: relations.cyclic,
            legacy_models: relations.legacy_models,
            model_subjects: self.model_subjects,
            diagnostics: self.diagnostics,
            text_models: self.text_models,
            environment_names: self.environment_names,
            lint_model_keys: self.lint_model_keys,
            lint_file_keys: self.lint_file_keys,
        };
        let rules: Option<RetainedRows> = self.rules;
        let ((gate, facts), rules) = rayon::join(
            || (json(&gate), json(&facts)),
            || {
                rules
                    .map(|rules| -> Result<(Vec<u8>, Vec<u8>), String> {
                        Ok((
                            without_derived_fields(json(&rules.request)?),
                            json(&rules.digests)?,
                        ))
                    })
                    .transpose()
            },
        );
        let mut sections: ImageSections = vec![
            (GATE_SECTION.to_owned(), gate?),
            (FACTS_SECTION.to_owned(), facts?),
        ];
        if let Some((request, digests)) = rules? {
            sections.push((RULES_SECTION.to_owned(), request));
            sections.push((RULE_DIGESTS_SECTION.to_owned(), digests));
        }
        Ok(sections)
    }

    /// The image stored in `sections` behind `gate`, or `None` when it is unreadable.
    pub(crate) fn decode(sections: &ImageSections, gate: ImageGate) -> Option<Self> {
        let (facts, rules) = rayon::join(
            || serde_json::from_slice::<StoredFacts>(section(sections, FACTS_SECTION)?).ok(),
            || -> Option<Option<RetainedRows>> {
                let Some(bytes) = section(sections, RULES_SECTION) else {
                    return Some(None);
                };
                let request: EvaluateRequest = serde_json::from_slice(bytes).ok()?;
                let digests: Vec<String> =
                    serde_json::from_slice(section(sections, RULE_DIGESTS_SECTION)?).ok()?;
                (digests.len() == request.models.len())
                    .then_some(Some(RetainedRows { request, digests }))
            },
        );
        let facts: StoredFacts = facts?;
        let types: Shapes = facts.types;
        let relations: ImageRelations = ImageRelations {
            complete: restored(facts.complete, &types)?,
            schemas: restored(facts.schemas, &types)?,
            nullability: facts.nullability,
            dependency_ordered: facts.dependency_ordered,
            cyclic: facts.cyclic,
            legacy_models: facts.legacy_models,
            types: Shapes::new(),
        };
        let model_shapes: Shapes = restored(facts.model_shapes, &types)?;
        Some(Self {
            format: gate.format,
            json_output: gate.json_output,
            models: gate.models,
            usages: facts.usages,
            tests: gate.tests,
            relations: ImageRelations { types, ..relations },
            fact_digests: gate.fact_digests,
            model_subjects: facts.model_subjects,
            diagnostics: facts.diagnostics,
            text_models: facts.text_models,
            environment_names: facts.environment_names,
            model_shapes,
            lint_model_keys: facts.lint_model_keys,
            lint_file_keys: facts.lint_file_keys,
            header_keys: gate.header_keys,
            rules: rules?,
        })
    }

    /// Every model whose reads include a relation of `names`, outside `names`.
    pub(crate) fn dependents(&self, names: &BTreeSet<String>) -> BTreeSet<String> {
        self.models
            .iter()
            .filter(|model| !names.contains(&model.name))
            .filter(|model| {
                model
                    .upstream
                    .iter()
                    .any(|(kind, name)| kind == "model" && names.contains(name))
            })
            .map(|model| model.name.clone())
            .collect()
    }
}
