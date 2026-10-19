//! What a full compile captures for its project image, and what a delta compile injects.
//!
//! Compiles run one at a time per process, but rules run on their own threads, so both the
//! capture and the injection live in process-wide slots rather than thread-local ones.

use std::collections::{BTreeMap, BTreeSet};
use std::sync::{Arc, Mutex, MutexGuard, PoisonError};

use sqlbuild_analysis::assembly::analysis_session::models::{RelationTables, SessionRequest};
use sqlbuild_cache::project_reuse::models::ImageSections;
use sqlbuild_rules::models::RetainedRows;

use crate::bindings::_helpers::compile_delta::image::PendingRules;

/// The facts a full compile leaves for its project image beyond its analysis record.
#[derive(Debug, Default)]
pub(crate) struct ImageCapture {
    /// The relation facts the model analysis session ended with.
    pub(crate) relations: Option<RelationTables>,
    /// The built-in rules request and its raw findings, before suppressions.
    pub(crate) rules: Option<CapturedRules>,
    /// Each custom-rule fact digest the custom rule cache compared, by fact key.
    pub(crate) fact_digests: BTreeMap<Vec<String>, String>,
    /// Whether the JSON report fell back to the standard library's serializer.
    pub(crate) stdlib_json: bool,
    /// Each model's scope usage digest, by model file path.
    pub(crate) usages: BTreeMap<String, String>,
    /// Each SQL test's compiled-artifact chain, by test key text.
    pub(crate) test_chains: Vec<CapturedTest>,
    /// Each project model's `(path, name, materialized)`, when custom rules ran.
    pub(crate) model_subjects: Option<Vec<(String, String, Option<String>)>>,
    /// Each compiled model's `(name, relative path, upstream (kind, name) pairs)`.
    pub(crate) models: Vec<CapturedModel>,
    /// Each report diagnostic as its JSON item text, with what it names.
    pub(crate) diagnostics: Vec<CapturedDiagnostic>,
    /// The text report's model lines `(name, failed, column count)`, when it rendered one.
    pub(crate) text_models: Option<Vec<(String, bool, i64)>>,
    /// The template environment names the compile read.
    pub(crate) environment_names: Vec<String>,
    /// Each discovered model's header keys, by model file path.
    pub(crate) header_keys:
        BTreeMap<String, crate::bindings::_helpers::compile_delta::header_keys::HeaderKeys>,
    /// Each model file's SQL lint cache key, in project model order.
    pub(crate) lint_model_keys: Option<Vec<(String, String)>>,
    /// Each other SQL file's lint cache key, in walk order.
    pub(crate) lint_file_keys: Option<Vec<(String, Option<String>)>>,
    /// The closed shape each model published for semantic checks, in publication order.
    pub(crate) model_shapes: Option<Vec<ModelShape>>,
    /// Why this compile cannot be the base of a delta compile, when something ruled it out.
    pub(crate) unsupported: Option<String>,
}

/// The built-in rules request a compile evaluated and its raw findings.
#[derive(Debug)]
pub(crate) struct CapturedRules {
    pub(crate) retained: RetainedRows,
}

/// One model's published `(column, type)` shape.
pub(crate) type ModelShape = (String, Vec<(String, String)>);

/// One compiled model's identity and references.
#[derive(Clone, Debug, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub(crate) struct CapturedModel {
    pub(crate) name: String,
    pub(crate) relative_path: String,
    pub(crate) upstream: Vec<(String, String)>,
}

/// One report diagnostic: its JSON text and the resource and file it names.
#[derive(Clone, Debug, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub(crate) struct CapturedDiagnostic {
    pub(crate) json: String,
    pub(crate) resource_name: Option<String>,
    pub(crate) paths: Vec<String>,
    /// Whether the diagnostic is an error.
    #[serde(default)]
    pub(crate) error: bool,
}

/// One SQL test's file and the models its compiled artifact is keyed by.
#[derive(Clone, Debug, serde::Serialize, serde::Deserialize)]
pub(crate) struct CapturedTest {
    pub(crate) key: String,
    pub(crate) relative_path: String,
    pub(crate) chain: Vec<String>,
}

/// What a delta compile hands the stages it reruns for the changed models.
#[derive(Debug, Default)]
pub(crate) struct DeltaInjection {
    /// Model files to discover, as project-relative POSIX paths.
    pub(crate) model_paths: BTreeSet<String>,
    /// SQL test files to discover, as project-relative POSIX paths.
    pub(crate) test_paths: BTreeSet<String>,
    /// The paths and names of every model the delta compile reruns.
    pub(crate) rerun_names: BTreeSet<String>,
    /// The project directory the stored compile and the delta compile both read.
    pub(crate) project_dir: std::path::PathBuf,
    /// Every model and SQL test file of the whole project, as project-relative POSIX paths.
    pub(crate) source_paths: BTreeSet<String>,
    /// Every model name of the whole project, which references resolve against.
    pub(crate) model_names: Vec<String>,
    /// The whole project's relation facts, injected for relations the delta does not analyse.
    pub(crate) relations: RelationTables,
    /// The whole project's built-in rules request, taken by the round that evaluates it.
    pub(crate) rules: Mutex<Option<PendingRules>>,
    /// The whole project's custom-rule fact digests.
    pub(crate) fact_digests: BTreeMap<Vec<String>, String>,
    /// Each project model's `(path, name, materialized)`, the custom-rule subjects.
    pub(crate) model_subjects: Option<Vec<(String, String, Option<String>)>>,
    /// The files that changed since the stored compile, as project-relative POSIX paths.
    pub(crate) changed_paths: BTreeSet<String>,
    /// Where loaded YAML documents are kept for later delta compiles.
    pub(crate) yaml_store: Option<std::path::PathBuf>,
    /// The only sources discovery keeps, those the rerun models read; `None` keeps every one.
    pub(crate) source_names: Option<BTreeSet<String>>,
    /// The whole project's SQL lint cache keys, as the image recorded them.
    pub(crate) lint_model_keys: Option<Vec<(String, String)>>,
    pub(crate) lint_file_keys: Option<Vec<(String, Option<String>)>>,
    /// The closed shapes the whole project's models published.
    pub(crate) model_shapes: Vec<ModelShape>,
    /// The whole project's text report model lines, with the rerun models' lines to replace.
    pub(crate) text_models: Vec<(String, bool, i64)>,
}

static CAPTURE: Mutex<Option<ImageCapture>> = Mutex::new(None);
static INJECTION: Mutex<Option<Arc<DeltaInjection>>> = Mutex::new(None);

fn locked<T>(slot: &Mutex<T>) -> MutexGuard<'_, T> {
    slot.lock().unwrap_or_else(PoisonError::into_inner)
}

/// Start capturing image facts for the compile about to run.
pub(crate) fn start_capture() {
    *locked(&CAPTURE) = Some(ImageCapture::default());
}

/// Stop capturing and take what was captured.
pub(crate) fn take_capture() -> Option<ImageCapture> {
    locked(&CAPTURE).take()
}

/// Whether the running compile captures image facts.
pub(crate) fn capturing() -> bool {
    locked(&CAPTURE).is_some()
}

/// Record into the capture, when one is running.
pub(crate) fn capture(record: impl FnOnce(&mut ImageCapture)) {
    if let Some(capture) = locked(&CAPTURE).as_mut() {
        record(capture);
    }
}

/// Mark the running capture as unusable as a delta base.
pub(crate) fn capture_unsupported(reason: &str) {
    capture(|capture| {
        if capture.unsupported.is_none() {
            capture.unsupported = Some(reason.to_owned());
        }
    });
}

/// Run `body` with `injection` visible to the stages a delta compile reruns.
///
/// Returns the injection back with the body's result, or `None` if something still holds it.
pub(crate) fn with_injection<T>(
    injection: DeltaInjection,
    body: impl FnOnce() -> T,
) -> (T, Option<DeltaInjection>) {
    *locked(&INJECTION) = Some(Arc::new(injection));
    let result: T = body();
    let injection: Option<Arc<DeltaInjection>> = locked(&INJECTION).take();
    (
        result,
        injection.and_then(|injection| Arc::try_unwrap(injection).ok()),
    )
}

/// The running delta compile's injection, if any.
pub(crate) fn injection() -> Option<Arc<DeltaInjection>> {
    locked(&INJECTION).clone()
}

/// Why the running delta compile cannot continue, once something ruled it out.
static UNSUPPORTED: Mutex<Option<String>> = Mutex::new(None);

/// Rule out the running delta compile: returns the error that unwinds to its fallback.
pub(crate) fn delta_unsupported(reason: &str) -> pyo3::PyErr {
    let mut slot = locked(&UNSUPPORTED);
    if slot.is_none() {
        *slot = Some(reason.to_owned());
    }
    pyo3::exceptions::PyRuntimeError::new_err(format!("delta compile unsupported: {reason}"))
}

/// In a delta compile that leaves errors to full compiles, stop once `failed` reports one.
pub(crate) fn stop_on_errors(failed: bool) -> pyo3::PyResult<()> {
    let errors_on_delta_path: bool =
        crate::bindings::_helpers::compile_delta::driver::ERRORS_ON_DELTA_PATH;
    if failed && !errors_on_delta_path && injection().is_some() {
        return Err(delta_unsupported("the edit reports errors"));
    }
    Ok(())
}

/// Take the reason the delta compile was ruled out, if any.
pub(crate) fn take_delta_unsupported() -> Option<String> {
    locked(&UNSUPPORTED).take()
}

/// The previous compile's digest of a custom-rule fact about a resource the delta did not rerun.
pub(crate) fn injected_fact_digest(key: &[String]) -> Option<String> {
    let injection: Arc<DeltaInjection> = injection()?;
    if key
        .iter()
        .skip(1)
        .any(|part| injection.rerun_names.contains(part))
    {
        return None;
    }
    injection.fact_digests.get(key).cloned()
}

/// Give a delta compile's analysis session the whole project's facts for relations it does not
/// analyse, and the whole project's analysis order.
pub(crate) fn inject_relations(request: &mut SessionRequest) -> pyo3::PyResult<()> {
    if !request.dynamic_families_by_table.is_empty() {
        capture_unsupported("a model declares dynamic column families");
    }
    let Some(injection) = injection() else {
        return Ok(());
    };
    if !request.dynamic_families_by_table.is_empty() {
        return Err(delta_unsupported(
            "a model declares dynamic column families",
        ));
    }
    let relations: &RelationTables = &injection.relations;
    request.forced_order = Some((relations.dependency_ordered, relations.cyclic));
    request.retain_relations = true;
    let analysed: BTreeSet<&str> = request
        .models
        .iter()
        .map(|model| model.name.as_str())
        .collect();
    for (table, injected) in [
        (&mut request.column_types, &relations.types),
        (&mut request.column_nullability, &relations.nullability),
        (&mut request.complete_schemas, &relations.complete),
    ] {
        let present: BTreeSet<String> = table.iter().map(|(name, _)| name.clone()).collect();
        table.extend(
            injected
                .iter()
                .filter(|(name, _)| !analysed.contains(name.as_str()) && !present.contains(name))
                .cloned(),
        );
    }
    Ok(())
}

/// What a delta compile's reuse record keeps of the stored compile it patched.
#[derive(Debug, Default)]
pub(crate) struct RecordMerge {
    /// Each stored artifact's stamp, verified by the reuse check, kept unless the delta wrote it.
    pub(crate) kept: Vec<sqlbuild_cache::project_snapshot::models::PathStamp>,
    /// The template environment names the stored compile read.
    pub(crate) environment_names: Vec<String>,
}

static PENDING_IMAGE: Mutex<Option<ImageSections>> = Mutex::new(None);
static RECORD_MERGE: Mutex<Option<RecordMerge>> = Mutex::new(None);

/// Hand the next reuse record the image to keep beside it.
pub(crate) fn set_pending_image(image: Option<ImageSections>) {
    *locked(&PENDING_IMAGE) = image;
}

/// The image the next reuse record keeps, taken.
pub(crate) fn take_pending_image() -> Option<ImageSections> {
    locked(&PENDING_IMAGE).take()
}

/// Hand the next reuse record what it keeps of the patched compile.
pub(crate) fn set_record_merge(merge: Option<RecordMerge>) {
    *locked(&RECORD_MERGE) = merge;
}

/// What the next reuse record keeps of the patched compile, taken.
pub(crate) fn take_record_merge() -> Option<RecordMerge> {
    locked(&RECORD_MERGE).take()
}

/// Forget every capture, injection and pending record fact, after a compile ends either way.
pub(crate) fn reset() {
    let _ = take_capture();
    *locked(&INJECTION) = None;
    let _ = take_delta_unsupported();
    set_pending_image(None);
    set_record_merge(None);
}
