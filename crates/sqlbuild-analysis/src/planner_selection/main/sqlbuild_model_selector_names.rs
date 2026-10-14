//! Resolve one SQLBuild-owned model selector core to model names.

use crate::planner_selection::constants::{
    FOLDER_SEPARATOR, PATH_PREFIX, TAG_PREFIX, WINDOWS_SEPARATOR,
};
use crate::planner_selection::models::{ModelSelectorNames, SelectableModel};

/// A model name, `tag:` or `path:` term's model names in model order; other terms match nothing.
pub fn sqlbuild_model_selector_names(models: &[SelectableModel], term: &str) -> ModelSelectorNames {
    if models.iter().any(|model| model.name == term) {
        return ModelSelectorNames {
            names: vec![term.to_owned()],
            translated: None,
        };
    }
    if let Some(tag) = term.strip_prefix(TAG_PREFIX) {
        return ModelSelectorNames {
            names: models
                .iter()
                .filter(|model| has_tag(model, tag))
                .map(|model| model.name.clone())
                .collect(),
            translated: None,
        };
    }
    let Some(raw_path) = term.strip_prefix(PATH_PREFIX) else {
        return ModelSelectorNames::default();
    };
    let path: String = raw_path.replace(WINDOWS_SEPARATOR, &FOLDER_SEPARATOR.to_string());
    let nested: String = format!("{path}{FOLDER_SEPARATOR}");
    ModelSelectorNames {
        names: models
            .iter()
            .filter(|model| model.folder == path || model.folder.starts_with(&nested))
            .map(|model| model.name.clone())
            .collect(),
        translated: (path != raw_path).then(|| format!("{PATH_PREFIX}{path}")),
    }
}

fn has_tag(model: &SelectableModel, tag: &str) -> bool {
    model.tags.iter().any(|candidate| candidate == tag)
}
