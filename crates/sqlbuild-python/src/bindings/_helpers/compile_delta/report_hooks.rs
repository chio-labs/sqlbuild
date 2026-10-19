//! Where the compile's report and output stages leave image facts or take a delta's injection.

use std::collections::{HashMap, HashSet};

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult};
use pyo3::types::{PyDict, PyDictMethods, PyStringMethods, PyTuple, PyTupleMethods};
use sqlbuild_core::cli_text::models::ModelLine;

use crate::bindings::_helpers::compile_command::report::diagnostic_item;
use crate::bindings::_helpers::compile_delta::context::{
    CapturedDiagnostic, CapturedModel, CapturedTest, ModelShape, capture, capture_unsupported,
    capturing, delta_unsupported, injection,
};
use crate::bindings::_helpers::compile_delta::coverage::{
    ModelCoverage, coverage_reasons, merged_coverage, merged_order,
};
use crate::bindings::_helpers::compile_outputs::json_report::plain_json;
use crate::bindings::_helpers::graph::project_graph::NativeProjectGraph;
use crate::bindings::_helpers::records::fields::field as native_field;

const SOURCES_KEY: &str = "sources";
const NAME_KEY: &str = "name";
/// The graph key kind of a model.
const MODEL_KIND: &str = "model";

/// The text report's model lines, captured or, in a delta, patched for the rerun models.
pub(crate) fn text_model_lines(models: Vec<ModelLine>) -> Vec<ModelLine> {
    let models: Vec<ModelLine> = match injection() {
        None => models,
        Some(injection) => {
            let mut fresh: HashMap<String, ModelLine> = models
                .into_iter()
                .map(|line| (line.name.clone(), line))
                .collect();
            injection
                .text_models
                .iter()
                .map(|(name, failed, column_count)| {
                    fresh.remove(name).unwrap_or_else(|| ModelLine {
                        name: name.clone(),
                        failed: *failed,
                        column_count: *column_count,
                    })
                })
                .collect()
        }
    };
    capture(|capture| {
        capture.text_models = Some(
            models
                .iter()
                .map(|line| (line.name.clone(), line.failed, line.column_count))
                .collect(),
        );
    });
    models
}

/// Record which models each SQL test's compiled artifact is keyed by.
fn record_test_chains_inner(tests: &Bound<'_, PyAny>, chains: &Bound<'_, PyAny>) -> PyResult<()> {
    if !capturing() {
        return Ok(());
    }
    let mut captured: Vec<CapturedTest> = Vec::new();
    for test in tests.try_iter()? {
        let test: Bound<'_, PyAny> = test?;
        let key: Bound<'_, PyAny> = native_field(&test, "key")?;
        let chain: Vec<String> = match chains.get_item(&key) {
            Ok(chain) => chain.extract()?,
            Err(_) => Vec::new(),
        };
        captured.push(CapturedTest {
            key: native_field(&test, "name")?.str()?.to_str()?.to_owned(),
            relative_path: native_field(&native_field(&test, "test_file")?, "relative_path")?
                .str()?
                .to_str()?
                .replace('\\', "/"),
            chain,
        });
    }
    capture(|capture| capture.test_chains = captured);
    Ok(())
}

/// Record the compiled models with their references, and the report's diagnostics.
fn record_compile_facts_inner(
    graph: &Bound<'_, PyAny>,
    diagnostics: &Bound<'_, PyTuple>,
) -> PyResult<()> {
    if !capturing() {
        return Ok(());
    }
    let native: Bound<'_, PyAny> = native_field(graph, "native")?;
    let graph_native: &NativeProjectGraph = native.cast::<NativeProjectGraph>()?.get();
    let mut models: Vec<CapturedModel> = Vec::new();
    for model in native_field(&native_field(graph, "project")?, "models")?.try_iter()? {
        let model: Bound<'_, PyAny> = model?;
        let name: String = native_field(&model, "name")?.extract()?;
        let upstream: Vec<(String, String)> =
            graph_native.upstream((MODEL_KIND.to_owned(), name.clone()));
        models.push(CapturedModel {
            name,
            relative_path: native_field(&model, "relative_path")?
                .str()?
                .to_str()?
                .replace('\\', "/"),
            upstream,
        });
    }
    let mut captured: Vec<CapturedDiagnostic> = Vec::new();
    for diagnostic in diagnostics.iter() {
        captured.push(captured_diagnostic(&diagnostic)?);
    }
    let test_count: usize = native_field(&native_field(graph, "project")?, "sql_tests")?.len()?;
    capture(|capture| {
        capture.models = models;
        capture.diagnostics = captured;
        if capture.test_chains.len() != test_count {
            capture
                .unsupported
                .get_or_insert_with(|| "the SQL tests' model chains were not recorded".to_owned());
        }
    });
    Ok(())
}

/// One diagnostic as its report JSON, with the resource and paths it names.
pub(crate) fn captured_diagnostic(diagnostic: &Bound<'_, PyAny>) -> PyResult<CapturedDiagnostic> {
    let item = diagnostic_item(diagnostic)?;
    let json: String = plain_json(item.as_any())?;
    let value: serde_json::Value = match serde_json::from_str(&json) {
        Ok(value) => value,
        Err(_malformed) => serde_json::Value::Null,
    };
    let text = |value: Option<&serde_json::Value>| -> Option<String> {
        value.and_then(serde_json::Value::as_str).map(str::to_owned)
    };
    let mut paths: Vec<String> = Vec::new();
    paths.extend(text(value.get("path")));
    paths.extend(text(
        value
            .get("location")
            .and_then(|location| location.get("path")),
    ));
    Ok(CapturedDiagnostic {
        json,
        resource_name: text(value.get("resource_name")),
        paths: paths
            .into_iter()
            .map(|path| path.replace('\\', "/"))
            .collect(),
        error: value.get("severity").and_then(serde_json::Value::as_str) == Some("error"),
    })
}

/// The partial-check reasons of the `fresh` models, merged in a delta with the stored models'.
pub(crate) fn semantic_reasons(
    order: Vec<(String, Vec<String>)>,
    fresh: Vec<ModelCoverage>,
) -> PyResult<Vec<(String, Vec<String>)>> {
    let (order, facts): (Vec<(String, Vec<String>)>, Vec<ModelCoverage>) = match injection() {
        None => (
            order,
            fresh.into_iter().filter(ModelCoverage::notable).collect(),
        ),
        Some(injection) => {
            let Some(stored) = &injection.coverage else {
                return Err(delta_unsupported(
                    "the stored compile recorded no semantic coverage",
                ));
            };
            (
                merged_order(&injection.coverage_order, &order),
                merged_coverage(stored, &fresh),
            )
        }
    };
    let reasons: Vec<(String, Vec<String>)> = coverage_reasons(&order, &facts);
    if capturing() {
        capture(|capture| {
            if capture.coverage.is_none() {
                capture.coverage = Some(facts);
            }
        });
    }
    Ok(reasons)
}

/// In a delta compile, publish the shapes of every model it does not compile again first.
pub(crate) fn inject_model_shapes(
    models: &[Bound<'_, PyAny>],
    shapes: &Bound<'_, PyDict>,
) -> PyResult<()> {
    let Some(injection) = injection() else {
        return Ok(());
    };
    let mut rerun: HashSet<String> = HashSet::with_capacity(models.len());
    for model in models {
        rerun.insert(native_field(model, "name")?.extract()?);
    }
    let py = shapes.py();
    for (name, columns) in &injection.model_shapes {
        if rerun.contains(name) {
            continue;
        }
        let shape: Bound<'_, PyDict> = PyDict::new(py);
        for (column, column_type) in columns {
            shape.set_item(column, column_type)?;
        }
        shapes.set_item(name, shape)?;
    }
    Ok(())
}

/// Record the model shapes the first semantic shape pass published.
fn record_model_shapes_inner(
    project: &Bound<'_, PyAny>,
    shapes: &Bound<'_, PyDict>,
) -> PyResult<()> {
    if !capturing() {
        return Ok(());
    }
    let mut names: HashSet<String> = HashSet::new();
    for model in native_field(project, "models")?.try_iter()? {
        names.insert(native_field(&model?, "name")?.extract()?);
    }
    if let Some(injection) = injection() {
        names.extend(injection.model_shapes.iter().map(|(name, _)| name.clone()));
    }
    let mut published: Vec<ModelShape> = Vec::new();
    for (name, shape) in shapes.iter() {
        let name: String = name.extract()?;
        if !names.contains(&name) {
            continue;
        }
        let shape: Bound<'_, PyDict> = shape.cast_into()?;
        let mut columns: Vec<(String, String)> = Vec::with_capacity(shape.len());
        for (column, column_type) in shape.iter() {
            columns.push((column.extract()?, column_type.extract()?));
        }
        published.push((name, columns));
    }
    capture(|capture| {
        if capture.model_shapes.is_none() {
            capture.model_shapes = Some(published);
        }
    });
    Ok(())
}

/// Run a capture hook; a failure only rules the compile out as a delta base.
fn guarded(hook: impl FnOnce() -> PyResult<()>) -> PyResult<()> {
    if !capturing() {
        return Ok(());
    }
    if let Err(error) = hook() {
        capture_unsupported(&format!("an image fact could not be recorded: {error}"));
    }
    Ok(())
}

/// Record which models each SQL test's compiled artifact is keyed by.
pub(crate) fn record_test_chains(
    tests: &Bound<'_, PyAny>,
    chains: &Bound<'_, PyAny>,
) -> PyResult<()> {
    guarded(|| record_test_chains_inner(tests, chains))
}

/// Record the compiled models with their references, and the report's diagnostics.
pub(crate) fn record_compile_facts(
    graph: &Bound<'_, PyAny>,
    diagnostics: &Bound<'_, PyTuple>,
) -> PyResult<()> {
    guarded(|| record_compile_facts_inner(graph, diagnostics))
}

/// Record the model shapes the first semantic shape pass published.
pub(crate) fn record_model_shapes(
    project: &Bound<'_, PyAny>,
    shapes: &Bound<'_, PyDict>,
) -> PyResult<()> {
    guarded(|| record_model_shapes_inner(project, shapes))
}

/// In a delta, add the text of files that stored diagnostics point into but were not rerun.
pub(crate) fn complete_source_texts(
    project: &Bound<'_, PyAny>,
    diagnostics: &[Bound<'_, PyAny>],
    texts: &Bound<'_, PyDict>,
) -> PyResult<()> {
    let Some(injection) = injection() else {
        return Ok(());
    };
    let _ = project;
    let project_dir: &std::path::Path = &injection.project_dir;
    let mut locations: Vec<Bound<'_, PyAny>> = Vec::new();
    for diagnostic in diagnostics {
        locations.push(native_field(diagnostic, "location")?);
        for item in native_field(diagnostic, "related_locations")?.try_iter()? {
            locations.push(native_field(&item?, "location")?);
        }
    }
    for location in locations.into_iter().filter(|location| !location.is_none()) {
        let path: Bound<'_, PyAny> = native_field(&location, "path")?;
        if texts.contains(&path)? {
            continue;
        }
        let relative: String = path.str()?.to_str()?.replace('\\', "/");
        if !injection.source_paths.contains(&relative) {
            continue;
        }
        if let Ok(text) = std::fs::read_to_string(project_dir.join(&relative)) {
            texts.set_item(&path, text)?;
        }
    }
    Ok(())
}

/// In a delta reading only some sources, drop every other loaded source YAML entry.
pub(crate) fn retain_read_sources(
    outcomes: &mut [sqlbuild_discovery::yaml_files::models::YamlFileOutcome],
) {
    use sqlbuild_config::models::ConfigValue;
    use sqlbuild_discovery::yaml_files::models::YamlFileOutcome;
    let Some(injection) = injection() else {
        return;
    };
    let Some(read) = injection.source_names.as_ref() else {
        return;
    };
    fn text(value: &ConfigValue) -> Option<&str> {
        match value {
            ConfigValue::String(text) => Some(text.as_str()),
            _ => None,
        }
    }
    for outcome in outcomes {
        let YamlFileOutcome::Loaded {
            value: ConfigValue::Map(entries),
            ..
        } = outcome
        else {
            continue;
        };
        for (key, value) in entries {
            if text(key) != Some(SOURCES_KEY) {
                continue;
            }
            let ConfigValue::List(sources) = value else {
                continue;
            };
            sources.retain(|source| {
                let name: Option<&str> = source.as_map().and_then(|entries| {
                    entries
                        .iter()
                        .find(|(key, _)| text(key) == Some(NAME_KEY))
                        .and_then(|(_, name)| text(name))
                });
                name.is_none_or(|name| read.contains(name))
            });
        }
    }
}
