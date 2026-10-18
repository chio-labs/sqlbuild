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
const IMAGE_FORMAT: &str = "sqlbuild-project-image-v1";
const FACTS_SECTION: &str = "facts";
const RULES_SECTION: &str = "rules";

/// Everything a delta compile reads of the compile it patches.
#[derive(Clone, Debug, Default, Serialize, Deserialize)]
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
    #[serde(skip)]
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

impl From<&ImageRelations> for RelationTables {
    fn from(relations: &ImageRelations) -> Self {
        Self {
            types: relations.types.clone(),
            nullability: relations.nullability.clone(),
            complete: relations.complete.clone(),
            schemas: relations.schemas.clone(),
            dependency_ordered: relations.dependency_ordered,
            cyclic: relations.cyclic,
            legacy_models: relations.legacy_models.clone(),
        }
    }
}

#[derive(Serialize, Deserialize)]
struct StoredRules {
    request: serde_json::Value,
    digests: Vec<String>,
}

/// Fields a request serializes but never reads back, by list; evaluation derives them again.
const DERIVED_FIELDS: [(&str, &str); 2] = [
    ("models", "empty_input_only_test_count"),
    ("sql_tests", "empty_input_only"),
];

fn stored_request(request: &EvaluateRequest) -> Result<serde_json::Value, String> {
    let mut value: serde_json::Value =
        serde_json::to_value(request).map_err(|error| error.to_string())?;
    for (list, field) in DERIVED_FIELDS {
        if let Some(items) = value
            .get_mut(list)
            .and_then(serde_json::Value::as_array_mut)
        {
            for item in items
                .iter_mut()
                .filter_map(serde_json::Value::as_object_mut)
            {
                item.remove(field);
            }
        }
    }
    Ok(value)
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
    pub(crate) fn encode(&self) -> Result<ImageSections, String> {
        let mut sections: ImageSections = vec![(
            FACTS_SECTION.to_owned(),
            serde_json::to_vec(self).map_err(|error| error.to_string())?,
        )];
        if let Some(rules) = &self.rules {
            let stored: StoredRules = StoredRules {
                request: stored_request(&rules.request)?,
                digests: rules.digests.clone(),
            };
            sections.push((
                RULES_SECTION.to_owned(),
                serde_json::to_vec(&stored).map_err(|error| error.to_string())?,
            ));
        }
        Ok(sections)
    }

    /// The image stored in `sections`, or `None` when it is unreadable or of another format.
    pub(crate) fn decode(sections: &ImageSections) -> Option<Self> {
        let section = |name: &str| {
            sections
                .iter()
                .find(|(section, _)| section == name)
                .map(|(_, bytes)| bytes.as_slice())
        };
        let mut image: Self = serde_json::from_slice(section(FACTS_SECTION)?).ok()?;
        if image.format != IMAGE_FORMAT {
            return None;
        }
        if let Some(bytes) = section(RULES_SECTION) {
            let stored: StoredRules = serde_json::from_slice(bytes).ok()?;
            let request: EvaluateRequest = serde_json::from_value(stored.request).ok()?;
            if stored.digests.len() != request.models.len() {
                return None;
            }
            image.rules = Some(RetainedRows {
                request,
                digests: stored.digests,
            });
        }
        Some(image)
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
