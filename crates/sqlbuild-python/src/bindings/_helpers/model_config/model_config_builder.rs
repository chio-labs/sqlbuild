//! Effective model config layered and templated natively, as `build_model_config` builds it.

use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyModule, PyModuleMethods, PyResult, Python};
use pyo3::types::{
    PyDict, PyDictMethods, PyList, PyListMethods, PyString, PyTuple, PyTupleMethods,
};
use pyo3::{IntoPyObject, PyErr, pyclass, pymethods};
use sqlbuild_model_config::config_presence::main::contains_template::contains_template;
use sqlbuild_model_config::config_presence::main::first_macro_path::first_macro_path;
use sqlbuild_model_config::config_presence::models::{MacroPath, Presence};
use sqlbuild_model_config::errors::ConfigError;
use sqlbuild_model_config::model_validation::main::retention_override::retention_override;
use sqlbuild_model_config::model_validation::main::table_type_override::table_type_override;
use sqlbuild_model_config::model_validation::models::{
    RetentionOverride, TableTypeOverride, ValidationStop,
};
use sqlbuild_model_config::path_defaults::main::select_path_default::select_path_default;
use sqlbuild_model_config::path_defaults::models::PathDefaultChoice;
use sqlbuild_model_config::templates::models::TemplateOptions;
use sqlbuild_model_config::types::AuthoredNode;

use crate::bindings::_helpers::boundary::panics::compiler_guard;
use crate::bindings::_helpers::model_config::authored_nodes::PyNode;
use crate::bindings::_helpers::model_config::config_errors::native_config_error;
use crate::bindings::_helpers::model_config::config_templates::{
    PythonHost, Stop, TemplateSources, expanded, template_error,
};

const HOOK_KEYS: [&str; 2] = ["pre_hooks", "post_hooks"];
/// Hook keys in the sorted order `validate_model_hook_config` checks them.
const SORTED_HOOK_KEYS: [&str; 2] = ["post_hooks", "pre_hooks"];
const MODEL_CONFIG_LABEL: &str = "model config";
const ENVIRONMENT_DATABASE_LABEL: &str = "environment database";
const ENVIRONMENT_SCHEMA_LABEL: &str = "environment schema";
const TAGS_KEY: &str = "tags";
const ROW_DIFF_EXCLUDE_COLUMNS_KEY: &str = "row_diff_exclude_columns";
const ROW_DIFF_TOLERANCES_KEY: &str = "row_diff_tolerances";
const AUDIT_OVERRIDE_SECTIONS: [&str; 2] = ["by_type", "by_column"];
const DATABASE_KEY: &str = "database";
const SCHEMA_KEY: &str = "schema";
const ALIAS_KEY: &str = "alias";
const MATERIALIZED_KEY: &str = "materialized";
const FULL_REFRESH_KEY: &str = "full_refresh";
const RETENTION_KEY: &str = "time_travel_retention";
const TABLE_TYPE_KEY: &str = "table_type";
const INCREMENTAL_MATERIALIZATION: &str = "incremental";
const PRESERVE_TARGET_VALUE: &str = "preserve";
const RUN_ID_CONTEXT: &str = "run.id";
const RUN_TARGET_CONTEXT: &str = "run.target";
const MODEL_NAME_CONTEXT: &str = "model.name";
const MODEL_DATABASE_CONTEXT: &str = "model.database";
const MODEL_SCHEMA_CONTEXT: &str = "model.schema";
const MODEL_ALIAS_CONTEXT: &str = "model.alias";
const DESTINATION_DATABASE_CONTEXT: &str = "destination.database";
const DESTINATION_SCHEMA_CONTEXT: &str = "destination.schema";
const DESTINATION_TABLE_CONTEXT: &str = "destination.table";
const DESTINATION_QUALIFIED_CONTEXT: &str = "destination.qualified";

/// Why the native build stops: a deferral to Python, the exact error, or a Python error.
enum Halt {
    Defer,
    Config(ConfigError),
    Error(PyErr),
}

impl From<PyErr> for Halt {
    fn from(error: PyErr) -> Self {
        Self::Error(error)
    }
}

impl From<ValidationStop> for Halt {
    fn from(stop: ValidationStop) -> Self {
        match stop {
            ValidationStop::Defer => Self::Defer,
            ValidationStop::Error(error) => Self::Config(error),
        }
    }
}

/// The `CompileInputError` `model '<name>' <text>`, raised by the model config build.
fn model_error(model_name: &str, text: &str) -> Halt {
    Halt::Config(ConfigError::compile(format!("model '{model_name}' {text}")))
}

type Built<T> = Result<T, Halt>;

/// The project-wide inputs every model's config build reads, captured once per compile.
#[pyclass(module = "sqlbuild._native", frozen)]
pub(crate) struct NativeModelConfigBuilder {
    defaults: Py<PyDict>,
    path_defaults: Py<PyDict>,
    path_keys: Vec<String>,
    hook_entry_types: Py<PyTuple>,
    variables: Py<PyDict>,
    environment: Py<PyAny>,
    target_name: Option<Py<PyAny>>,
    run_id: Py<PyAny>,
    target_namespace: Option<(Py<PyAny>, Py<PyAny>)>,
}

/// One model's built config before Python wraps it in `CompileModelConfig`.
struct BuiltConfig<'py> {
    values: Bound<'py, PyDict>,
    header_keys: Vec<String>,
    logical_schema: Option<Bound<'py, PyAny>>,
    layer_schema_configured: bool,
    logical_database: Option<Bound<'py, PyAny>>,
    retention: RetentionOverride,
    table_type: TableTypeOverride,
    reads: Vec<(&'static str, String)>,
}

#[pymethods]
impl NativeModelConfigBuilder {
    #[new]
    fn new(
        layers: (Bound<'_, PyDict>, Bound<'_, PyDict>, Bound<'_, PyTuple>),
        sources: (Bound<'_, PyDict>, Bound<'_, PyAny>),
        run: (Bound<'_, PyAny>, Bound<'_, PyAny>),
        target_namespace: Option<(Bound<'_, PyAny>, Bound<'_, PyAny>)>,
    ) -> PyResult<Self> {
        let (defaults, path_defaults, hook_entry_types) = layers;
        let path_keys = path_defaults
            .keys()
            .iter()
            .map(|key| key.extract::<String>())
            .collect::<PyResult<Vec<_>>>()?;
        let (target_name, run_id) = run;
        Ok(Self {
            defaults: defaults.unbind(),
            path_defaults: path_defaults.unbind(),
            path_keys,
            hook_entry_types: hook_entry_types.unbind(),
            variables: sources.0.unbind(),
            environment: sources.1.unbind(),
            target_name: (!target_name.is_none()).then(|| target_name.unbind()),
            run_id: run_id.unbind(),
            target_namespace: target_namespace
                .map(|(database, schema)| (database.unbind(), schema.unbind())),
        })
    }

    /// Return the selected path-default key, `None`, or the conflict error Python raises.
    fn path_default(&self, py: Python<'_>, model_path: &str) -> PyResult<Py<PyAny>> {
        compiler_guard(|| {
            Ok(match select_path_default(model_path, &self.path_keys) {
                PathDefaultChoice::Selected(key) => key.into_pyobject(py)?.into_any().unbind(),
                PathDefaultChoice::Conflict(error) => native_config_error(py, error)?.into_any(),
            })
        })
    }

    /// Return the built config parts, the first error, or `None` when Python must build it.
    fn build<'py>(
        &self,
        py: Python<'py>,
        header: Bound<'py, PyDict>,
        matched_path_default: Option<&str>,
        model_name: &str,
    ) -> PyResult<Option<Py<PyAny>>> {
        compiler_guard(
            || match self.build_config(py, &header, matched_path_default, model_name) {
                Ok(built) => built_tuple(py, built).map(|built| Some(built.into_any().unbind())),
                Err(Halt::Defer) => Ok(None),
                Err(Halt::Config(error)) => Ok(Some(native_config_error(py, error)?.into_any())),
                Err(Halt::Error(error)) => Err(error),
            },
        )
    }
}

impl NativeModelConfigBuilder {
    fn build_config<'py>(
        &self,
        py: Python<'py>,
        header: &Bound<'py, PyDict>,
        matched_path_default: Option<&str>,
        model_name: &str,
    ) -> Built<BuiltConfig<'py>> {
        check_header_tags(header, model_name)?;
        let path_values = matched_path_default
            .map(|key| self.path_default_values(py, key))
            .transpose()?;
        let mut layered = self.project_defaults(py)?;
        if let Some(path_values) = &path_values {
            layered = merged_layer(py, &layered, path_values)?;
        }
        let layered = merged_layer(py, &layered, header)?;
        self.check_hooks(py, &layered, model_name)?;
        let mut hooks: Vec<(&str, Bound<'py, PyAny>)> = Vec::new();
        for key in HOOK_KEYS {
            if let Some(value) = layered.get_item(key)? {
                hooks.push((key, value));
                layered.del_item(key)?;
            }
        }
        let has_templates = present(contains_template(&PyNode(layered.clone().into_any())))?;
        let mut expansion = Expansion {
            builder: self,
            py,
            model_name,
            reads: Vec::new(),
        };
        let model_values = if has_templates {
            let early = expansion.expand(
                &layered,
                &self.variables.bind(py).clone(),
                expansion.run_context()?,
                (true, MODEL_CONFIG_LABEL),
            )?;
            let empty = PyDict::new(py);
            let first = expansion.expand(
                &early,
                &empty,
                expansion.model_context(&early, false)?,
                (true, MODEL_CONFIG_LABEL),
            )?;
            expansion.expand(
                &first,
                &empty,
                expansion.model_context(&first, false)?,
                (true, MODEL_CONFIG_LABEL),
            )?
        } else {
            layered
        };
        let logical_schema = string_entry(&model_values, SCHEMA_KEY)?;
        let logical_database = string_entry(&model_values, DATABASE_KEY)?;
        let layer_schema_configured = header.contains(SCHEMA_KEY)?
            || path_values
                .as_ref()
                .map(|values| values.contains(SCHEMA_KEY))
                .transpose()?
                .unwrap_or(false);
        let namespaced =
            expansion.namespaced_values(&model_values, &logical_database, &logical_schema)?;
        let needs_target_templates = has_templates
            || [DATABASE_KEY, SCHEMA_KEY]
                .iter()
                .map(|key| entry_has_template(&namespaced, key))
                .collect::<Built<Vec<bool>>>()?
                .into_iter()
                .any(|found| found);
        let resolved = if needs_target_templates {
            let empty = PyDict::new(py);
            expansion.expand(
                &namespaced,
                &empty,
                expansion.model_context(&namespaced, true)?,
                (false, MODEL_CONFIG_LABEL),
            )?
        } else {
            namespaced
        };
        for (key, value) in hooks {
            resolved.set_item(key, value)?;
        }
        let values = storage_free_values(py, &resolved, header)?;
        let retention = retention_override(
            header.get_item(RETENTION_KEY)?.map(PyNode).as_ref(),
            model_name,
        )?;
        let table_type = table_type_override(
            header.get_item(TABLE_TYPE_KEY)?.map(PyNode).as_ref(),
            model_name,
        )?;
        check_no_config_macros(&values)?;
        Ok(BuiltConfig {
            values,
            header_keys: sorted_keys(header)?,
            logical_schema,
            layer_schema_configured,
            logical_database,
            retention,
            table_type,
            reads: expansion.reads,
        })
    }

    fn path_default_values<'py>(&self, py: Python<'py>, key: &str) -> Built<Bound<'py, PyDict>> {
        let values = self
            .path_defaults
            .bind(py)
            .get_item(key)?
            .ok_or(Halt::Defer)?;
        values.downcast_into::<PyDict>().map_err(|_| Halt::Defer)
    }

    /// Return a fresh `project_defaults_to_mapping` result, with its own `tags` list.
    fn project_defaults<'py>(&self, py: Python<'py>) -> Built<Bound<'py, PyDict>> {
        let defaults = self.defaults.bind(py).copy()?;
        if let Some(tags) = defaults.get_item(TAGS_KEY)? {
            let tags = tags.downcast_into::<PyList>().map_err(|_| Halt::Defer)?;
            defaults.set_item(TAGS_KEY, PyList::new(py, tags.iter())?)?;
        }
        Ok(defaults)
    }

    /// Check hook keys as `validate_model_hook_config` does.
    fn check_hooks(
        &self,
        py: Python<'_>,
        values: &Bound<'_, PyDict>,
        model_name: &str,
    ) -> Built<()> {
        let entry_types = self.hook_entry_types.bind(py);
        for key in SORTED_HOOK_KEYS {
            let Some(value) = values.get_item(key)? else {
                continue;
            };
            let Some(entries) = sequence_items(&value) else {
                return Err(model_error(
                    model_name,
                    &format!("{key} must be a list of typed hook entries"),
                ));
            };
            for entry in entries {
                if !entry.is_instance(entry_types)? {
                    return Err(model_error(
                        model_name,
                        &format!(
                            "{key} entries must use typed inline_sql(...), sql(...), or \
                             python(...) hook syntax"
                        ),
                    ));
                }
            }
        }
        Ok(())
    }
}

/// The template expansions of one model's build and the reads they recorded.
struct Expansion<'a, 'py> {
    builder: &'a NativeModelConfigBuilder,
    py: Python<'py>,
    model_name: &'a str,
    reads: Vec<(&'static str, String)>,
}

impl<'py> Expansion<'_, 'py> {
    /// Expand `values`; `scope` is `preserve_unknown_context` and the context label.
    fn expand(
        &mut self,
        values: &Bound<'py, PyDict>,
        variables: &Bound<'py, PyDict>,
        context: Bound<'py, PyDict>,
        scope: (bool, &str),
    ) -> Built<Bound<'py, PyDict>> {
        let result = self.expand_value(values.as_any(), variables, context, scope)?;
        result.downcast_into::<PyDict>().map_err(|_| Halt::Defer)
    }

    fn expand_value(
        &mut self,
        value: &Bound<'py, PyAny>,
        variables: &Bound<'py, PyDict>,
        context: Bound<'py, PyDict>,
        scope: (bool, &str),
    ) -> Built<Bound<'py, PyAny>> {
        let (preserve_unknown_context, label) = scope;
        let environment = self.builder.environment.bind(self.py).clone();
        let host = PythonHost::new(
            self.py,
            TemplateSources(variables.clone(), environment, context),
        );
        let options = TemplateOptions {
            allow_context: true,
            preserve_context_tokens: false,
            preserve_unknown_context,
        };
        let result = expanded(&host, value, options);
        self.reads.extend(host.into_reads());
        result.map_err(|stop| match stop {
            Stop::Failure(failure) => {
                template_error(&failure, label).map_or(Halt::Defer, Halt::Config)
            }
            Stop::Python(error) => Halt::Error(error),
        })
    }

    fn run_context(&self) -> Built<Bound<'py, PyDict>> {
        let context = PyDict::new(self.py);
        context.set_item(RUN_ID_CONTEXT, self.builder.run_id.bind(self.py))?;
        context.set_item(
            RUN_TARGET_CONTEXT,
            self.optional(self.builder.target_name.as_ref()),
        )?;
        Ok(context)
    }

    fn optional(&self, value: Option<&Py<PyAny>>) -> Bound<'py, PyAny> {
        value.map_or_else(
            || self.py.None().into_bound(self.py),
            |item| item.bind(self.py).clone(),
        )
    }

    /// Return `build_model_context_values` for these values.
    fn model_context(
        &self,
        values: &Bound<'py, PyDict>,
        include_target_values: bool,
    ) -> Built<Bound<'py, PyDict>> {
        let py = self.py;
        let none = py.None().into_bound(py);
        let database = string_entry(values, DATABASE_KEY)?;
        let schema = string_entry(values, SCHEMA_KEY)?;
        let alias = match string_entry(values, ALIAS_KEY)? {
            Some(alias) => alias,
            None => PyString::new(py, self.model_name).into_any(),
        };
        let context = self.run_context()?;
        context.set_item(MODEL_NAME_CONTEXT, self.model_name)?;
        context.set_item(MODEL_DATABASE_CONTEXT, database.as_ref().unwrap_or(&none))?;
        context.set_item(MODEL_SCHEMA_CONTEXT, schema.as_ref().unwrap_or(&none))?;
        context.set_item(MODEL_ALIAS_CONTEXT, &alias)?;
        if !include_target_values {
            return Ok(context);
        }
        let qualified = match (&database, &schema) {
            (Some(database), Some(schema)) => Some(format!(
                "{}.{}.{}",
                text_of(database)?,
                text_of(schema)?,
                text_of(&alias)?
            )),
            (None, Some(schema)) => Some(format!("{}.{}", text_of(schema)?, text_of(&alias)?)),
            _ => None,
        };
        context.set_item(
            DESTINATION_DATABASE_CONTEXT,
            database.as_ref().unwrap_or(&none),
        )?;
        context.set_item(DESTINATION_SCHEMA_CONTEXT, schema.as_ref().unwrap_or(&none))?;
        context.set_item(DESTINATION_TABLE_CONTEXT, &alias)?;
        context.set_item(DESTINATION_QUALIFIED_CONTEXT, qualified)?;
        Ok(context)
    }

    /// Check preserved namespaces and apply `apply_environment_database_schema_overrides`.
    fn namespaced_values(
        &mut self,
        values: &Bound<'py, PyDict>,
        logical_database: &Option<Bound<'py, PyAny>>,
        logical_schema: &Option<Bound<'py, PyAny>>,
    ) -> Built<Bound<'py, PyDict>> {
        let overridden = values.copy()?;
        let Some((database, schema)) = &self.builder.target_namespace else {
            return Ok(overridden);
        };
        let py = self.py;
        let namespace = [
            (
                DATABASE_KEY,
                database.bind(py).clone(),
                logical_database.is_some(),
            ),
            (
                SCHEMA_KEY,
                schema.bind(py).clone(),
                logical_schema.is_some(),
            ),
        ];
        let preserved =
            |value: &Bound<'py, PyAny>| PyNode(value.clone()).is_text(PRESERVE_TARGET_VALUE);
        let missing: Vec<&str> = namespace
            .iter()
            .filter(|(_, value, logical)| preserved(value) && !logical)
            .map(|(key, _, _)| *key)
            .collect();
        if !missing.is_empty() {
            let dimensions = missing.join(" and ");
            return Err(Halt::Config(
                ConfigError::compile(format!(
                    "Model '{}' has no logical {dimensions}, but the selected target sets \
                     {dimensions} to 'preserve'",
                    self.model_name
                ))
                .with_help(format!(
                    "Set {dimensions} on the resource or its defaults, or configure a literal \
                     target {dimensions}."
                )),
            ));
        }
        let context = self.model_context(values, false)?;
        for (key, value, _) in namespace {
            if value.is_none() || preserved(&value) {
                continue;
            }
            let label = if key == DATABASE_KEY {
                ENVIRONMENT_DATABASE_LABEL
            } else {
                ENVIRONMENT_SCHEMA_LABEL
            };
            let variables = self.builder.variables.bind(py).clone();
            let expanded_value =
                self.expand_value(&value, &variables, context.copy()?, (false, label))?;
            overridden.set_item(key, expanded_value)?;
        }
        Ok(overridden)
    }
}

/// Merge `overlay` over a copy of `base` as `_merged_with_tag_union` does.
fn merged_layer<'py>(
    py: Python<'py>,
    base: &Bound<'py, PyDict>,
    overlay: &Bound<'py, PyDict>,
) -> Built<Bound<'py, PyDict>> {
    let result = base.copy()?;
    result.update(overlay.as_mapping())?;
    if let (Some(base_tags), Some(overlay_tags)) =
        (set_entry(base, TAGS_KEY)?, set_entry(overlay, TAGS_KEY)?)
    {
        let tags = merged_strings(&base_tags, &overlay_tags)?;
        result.set_item(TAGS_KEY, PyList::new(py, tags)?)?;
    }
    if let (Some(base_columns), Some(overlay_columns)) = (
        set_entry(base, ROW_DIFF_EXCLUDE_COLUMNS_KEY)?,
        set_entry(overlay, ROW_DIFF_EXCLUDE_COLUMNS_KEY)?,
    ) {
        let columns = merged_strings(&base_columns, &overlay_columns)?;
        result.set_item(ROW_DIFF_EXCLUDE_COLUMNS_KEY, PyTuple::new(py, columns)?)?;
    }
    if let (Some(base_tolerances), Some(overlay_tolerances)) = (
        set_entry(base, ROW_DIFF_TOLERANCES_KEY)?,
        set_entry(overlay, ROW_DIFF_TOLERANCES_KEY)?,
    ) {
        result.set_item(
            ROW_DIFF_TOLERANCES_KEY,
            merged_tolerances(&base_tolerances, &overlay_tolerances)?,
        )?;
    }
    Ok(result)
}

/// Return the strings of `base` then the new strings of `overlay`, as `_merge_string_sequence`.
fn merged_strings(base: &Bound<'_, PyAny>, overlay: &Bound<'_, PyAny>) -> Built<Vec<String>> {
    let mut merged = string_items(base)?;
    for item in string_items(overlay)? {
        if !merged.contains(&item) {
            merged.push(item);
        }
    }
    Ok(merged)
}

/// Return `_as_string_list(value)` when every item is a string.
fn string_items(value: &Bound<'_, PyAny>) -> Built<Vec<String>> {
    let Some(items) = sequence_items(value) else {
        return Ok(Vec::new());
    };
    items
        .iter()
        .map(|item| PyNode(item.clone()).text().ok_or(Halt::Defer))
        .collect()
}

/// Deep-merge row-diff tolerances by section as `_merge_row_diff_tolerances_mapping` does.
fn merged_tolerances<'py>(
    base: &Bound<'py, PyAny>,
    overlay: &Bound<'py, PyAny>,
) -> Built<Bound<'py, PyAny>> {
    let (Ok(base), Ok(overlay)) = (base.downcast::<PyDict>(), overlay.downcast::<PyDict>()) else {
        return Ok(overlay.clone());
    };
    let merged = base.copy()?;
    for section in AUDIT_OVERRIDE_SECTIONS {
        let Some(overlay_section) = set_entry(overlay, section)? else {
            continue;
        };
        let base_section = set_entry(base, section)?;
        if let Some(base_section) = &base_section
            && let (Ok(base_section), Ok(overlay_mapping)) = (
                base_section.downcast::<PyDict>(),
                overlay_section.downcast::<PyDict>(),
            )
        {
            let section_values = base_section.copy()?;
            section_values.update(overlay_mapping.as_mapping())?;
            merged.set_item(section, section_values)?;
        } else {
            merged.set_item(section, &overlay_section)?;
        }
    }
    for (key, value) in overlay.iter() {
        if key.is_instance_of::<PyString>()
            && !AUDIT_OVERRIDE_SECTIONS
                .iter()
                .any(|section| PyNode(key.clone()).is_text(section))
        {
            merged.set_item(key, value)?;
        }
    }
    Ok(merged.into_any())
}

/// Return `values.get(key)` unless it is absent or `None`.
fn set_entry<'py>(values: &Bound<'py, PyDict>, key: &str) -> Built<Option<Bound<'py, PyAny>>> {
    Ok(values.get_item(key)?.filter(|value| !value.is_none()))
}

/// Return the value when it is a string, as `isinstance(raw, str)` keeps it.
fn string_entry<'py>(values: &Bound<'py, PyDict>, key: &str) -> Built<Option<Bound<'py, PyAny>>> {
    Ok(values
        .get_item(key)?
        .filter(|value| value.is_instance_of::<PyString>()))
}

fn text_of(value: &Bound<'_, PyAny>) -> Built<String> {
    PyNode(value.clone()).text().ok_or(Halt::Defer)
}

fn sequence_items<'py>(value: &Bound<'py, PyAny>) -> Option<Vec<Bound<'py, PyAny>>> {
    if let Ok(items) = value.downcast::<PyList>() {
        Some(items.iter().collect())
    } else if let Ok(items) = value.downcast::<PyTuple>() {
        Some(items.iter().collect())
    } else {
        None
    }
}

fn present(presence: Presence) -> Built<bool> {
    match presence {
        Presence::Present => Ok(true),
        Presence::Absent => Ok(false),
        Presence::Deferred => Err(Halt::Defer),
    }
}

fn entry_has_template(values: &Bound<'_, PyDict>, key: &str) -> Built<bool> {
    match values.get_item(key)? {
        Some(value) => present(contains_template(&PyNode(value))),
        None => Ok(false),
    }
}

/// Check header tags as `_validate_model_header_tags` does.
fn check_header_tags(header: &Bound<'_, PyDict>, model_name: &str) -> Built<()> {
    let Some(tags) = set_entry(header, TAGS_KEY)? else {
        return Ok(());
    };
    let Ok(tags) = tags.downcast::<PyList>() else {
        return Err(model_error(model_name, "tags must be a list"));
    };
    if tags.iter().all(|tag| tag.is_instance_of::<PyString>()) {
        Ok(())
    } else {
        Err(model_error(model_name, "tags entries must be strings"))
    }
}

/// Drop storage keys, then `full_refresh` where `build_model_config` drops it.
fn storage_free_values<'py>(
    py: Python<'py>,
    resolved: &Bound<'py, PyDict>,
    header: &Bound<'py, PyDict>,
) -> Built<Bound<'py, PyDict>> {
    if let Some(materialized) = set_entry(resolved, MATERIALIZED_KEY)?
        && !materialized.is_instance_of::<PyString>()
    {
        return Err(Halt::Defer);
    }
    let values = PyDict::new(py);
    for (key, value) in resolved.iter() {
        let storage = [RETENTION_KEY, TABLE_TYPE_KEY]
            .iter()
            .any(|name| PyNode(key.clone()).is_text(name));
        if !storage {
            values.set_item(key, value)?;
        }
    }
    let incremental = values
        .get_item(MATERIALIZED_KEY)?
        .is_some_and(|value| PyNode(value).is_text(INCREMENTAL_MATERIALIZATION));
    if !header.contains(FULL_REFRESH_KEY)? && !incremental && values.contains(FULL_REFRESH_KEY)? {
        values.del_item(FULL_REFRESH_KEY)?;
    }
    Ok(values)
}

/// Raise for the first config field outside hooks holding a macro call, as Python's walk does.
fn check_no_config_macros(values: &Bound<'_, PyDict>) -> Built<()> {
    match first_macro_path(&PyNode(values.clone().into_any()), &HOOK_KEYS) {
        MacroPath::Absent => Ok(()),
        MacroPath::Deferred => Err(Halt::Defer),
        MacroPath::Found(path) => Err(Halt::Config(ConfigError::compile(format!(
            "model config field '{}' does not allow macros",
            path.join(".")
        )))),
    }
}

fn sorted_keys(header: &Bound<'_, PyDict>) -> Built<Vec<String>> {
    let mut keys = header
        .keys()
        .iter()
        .map(|key| {
            if key.is_exact_instance_of::<PyString>() {
                key.extract::<String>().map_err(Halt::from)
            } else {
                Err(Halt::Defer)
            }
        })
        .collect::<Built<Vec<_>>>()?;
    keys.sort();
    Ok(keys)
}

fn built_tuple<'py>(py: Python<'py>, built: BuiltConfig<'py>) -> PyResult<Bound<'py, PyTuple>> {
    let retention = match built.retention {
        RetentionOverride::Inherit => None,
        RetentionOverride::Unmanaged => Some((None, true)),
        RetentionOverride::Days(days) => Some((Some(days), false)),
    };
    let table_type = match built.table_type {
        TableTypeOverride::Inherit => None,
        TableTypeOverride::Permanent => Some("permanent"),
        TableTypeOverride::Transient => Some("transient"),
    };
    (
        built.values,
        PyTuple::new(py, built.header_keys)?,
        (
            built.logical_schema,
            built.layer_schema_configured,
            built.logical_database,
        ),
        (retention, table_type),
        built.reads,
    )
        .into_pyobject(py)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<NativeModelConfigBuilder>()?;
    Ok(())
}
