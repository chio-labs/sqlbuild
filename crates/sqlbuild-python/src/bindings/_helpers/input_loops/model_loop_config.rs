//! A model's effective config: its path default, the native build, and reuse across models.

use std::cell::RefCell;
use std::collections::HashMap;

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use pyo3::types::{PyDict, PyDictMethods, PyString, PyStringMethods, PyTuple};
use sqlbuild_discovery::model_files::models::HeaderFacts;
use sqlbuild_model_config::config_presence::main::blocks_config_reuse::blocks_config_reuse;
use sqlbuild_model_config::config_presence::main::contains_template::contains_template;
use sqlbuild_model_config::config_presence::main::mutable_config_value::mutable_config_value;

use crate::bindings::_helpers::input_loops::model_loop::{LoopContext, config_error};
use crate::bindings::_helpers::model_config::authored_nodes::PyNode;
use crate::bindings::_helpers::model_config::config_classes::{ConfigClasses, config_fields, view};
use crate::bindings::_helpers::model_config::model_config_builder::{
    BuiltConfig, ConfigBuild, NativeModelConfigBuilder,
};

const COLUMNS_KEY: &str = "columns";
const DESCRIPTION_KEY: &str = "description";
const HOOK_KEYS: [&str; 2] = ["pre_hooks", "post_hooks"];
/// What a path default's models inherit, and whether a model may reuse another's config.
struct InheritedLayer<'py> {
    reusable: bool,
    values: Bound<'py, PyDict>,
}

/// A reusable config: its values without header metadata, and its other fields.
struct ReusedConfig<'py> {
    values: Bound<'py, PyDict>,
    fields: Bound<'py, PyDict>,
}

/// `_ReusableModelConfigCache` for one compile.
#[derive(Default)]
pub(crate) struct ModelConfigs<'py> {
    layers: RefCell<HashMap<Option<String>, InheritedLayer<'py>>>,
    reused: RefCell<HashMap<Option<String>, ReusedConfig<'py>>>,
}

impl<'py> ModelConfigs<'py> {
    /// `_effective_model_config`: the reused or natively built config of one model.
    pub(crate) fn effective(
        &self,
        context: &LoopContext<'_, 'py>,
        header: &Bound<'py, PyDict>,
        model: (&str, &str),
        facts: Option<&HeaderFacts>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let (name, relative_path) = model;
        let py: Python<'py> = header.py();
        let classes: &ConfigClasses<'py> = &context.classes.config;
        let builder: &NativeModelConfigBuilder = classes.builder.get();
        let matched: Option<String> = builder
            .selected_path_default(py, relative_path)?
            .map_err(|error| config_error(error.bind(py).as_any(), None))?;
        let metadata: Option<Bound<'py, PyDict>> = reusable_metadata(header, facts)?;
        let reusable: bool = match metadata {
            Some(_) => self.reusable(context, &matched)?,
            None => false,
        };
        if reusable
            && let Some(metadata) = &metadata
            && let Some(cached) = self.reused.borrow().get(&matched)
        {
            let values: Bound<'py, PyDict> = cached.values.copy()?;
            values.update(metadata.as_mapping())?;
            return view(classes, &values, &cached.fields);
        }
        let built: ConfigBuild<'py> =
            builder.built(py, (header, facts), matched.as_deref(), name)?;
        let built: BuiltConfig<'py> = match built {
            ConfigBuild::Built(built) => built,
            ConfigBuild::Rejected(error) => {
                return Err(config_error(error.bind(py).as_any(), None));
            }
        };
        let fields: Bound<'py, PyDict> = config_fields(classes, &built, matched.as_deref())?;
        if reusable && let Some(metadata) = &metadata {
            self.remember(&matched, metadata, &built.values, &fields)?;
        }
        view(classes, &built.values, &fields)
    }

    /// `_is_reusable`: no templates in the inherited values or the target namespace, nothing mutable.
    fn reusable(&self, context: &LoopContext<'_, 'py>, matched: &Option<String>) -> PyResult<bool> {
        if let Some(layer) = self.layers.borrow().get(matched) {
            return Ok(layer.reusable);
        }
        let py: Python<'py> = context.host.py();
        let builder: &NativeModelConfigBuilder = context.classes.config.builder.get();
        let values: Bound<'py, PyDict> = builder
            .inherited_values(py, matched.as_deref())?
            .map_err(|error| config_error(error.bind(py).as_any(), None))?;
        let checked: Bound<'py, PyTuple> = PyTuple::new(
            py,
            [values.as_any(), builder.target_namespace(py)?.as_any()],
        )?;
        let mut mutable: bool = false;
        for key in HOOK_KEYS {
            mutable |= values.contains(key)?;
        }
        for (_, value) in values.iter() {
            mutable |= mutable_config_value(&PyNode(value));
        }
        let reusable: bool = !contains_template(&PyNode(checked.into_any())) && !mutable;
        self.layers
            .borrow_mut()
            .insert(matched.clone(), InheritedLayer { reusable, values });
        Ok(reusable)
    }

    /// `remember`: the built values with header metadata replaced by what the model inherits.
    fn remember(
        &self,
        matched: &Option<String>,
        metadata: &Bound<'py, PyDict>,
        values: &Bound<'py, PyDict>,
        fields: &Bound<'py, PyDict>,
    ) -> PyResult<()> {
        let py: Python<'py> = values.py();
        let layers = self.layers.borrow();
        let Some(inherited) = layers.get(matched) else {
            return Ok(());
        };
        let reusable_values: Bound<'py, PyDict> = PyDict::new(py);
        for (key, value) in values.iter() {
            if !metadata.contains(&key)? {
                reusable_values.set_item(key, value)?;
            }
        }
        for key in metadata.keys() {
            if let Some(value) = inherited.values.get_item(&key)? {
                reusable_values.set_item(key, value)?;
            }
        }
        self.reused.borrow_mut().insert(
            matched.clone(),
            ReusedConfig {
                values: reusable_values,
                fields: fields.clone(),
            },
        );
        Ok(())
    }
}

/// `_reusable_metadata`: the header when only plain columns and description vary, else `None`.
fn reusable_metadata<'py>(
    header: &Bound<'py, PyDict>,
    facts: Option<&HeaderFacts>,
) -> PyResult<Option<Bound<'py, PyDict>>> {
    let py: Python<'py> = header.py();
    if header.is_empty() {
        return Ok(Some(PyDict::new(py)));
    }
    for key in header.keys() {
        let reusable_key: bool = key.downcast::<PyString>().is_ok_and(|key| {
            key.to_str()
                .is_ok_and(|key| key == COLUMNS_KEY || key == DESCRIPTION_KEY)
        });
        if !reusable_key {
            return Ok(None);
        }
    }
    for key in [DESCRIPTION_KEY, COLUMNS_KEY] {
        let Some(value) = header.get_item(key)? else {
            continue;
        };
        let blocks: bool = match facts.and_then(|facts| facts.entry(key)) {
            Some(entry) => entry.blocks_reuse,
            None => blocks_config_reuse(&PyNode(value)),
        };
        if blocks {
            return Ok(None);
        }
    }
    Ok(Some(header.clone()))
}
