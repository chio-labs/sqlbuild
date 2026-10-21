//! Process-wide slots for what a full compile captures and what a delta compile injects.

use std::collections::{BTreeMap, BTreeSet};
use std::sync::{Arc, Mutex, MutexGuard, PoisonError};

use pyo3::prelude::PyResult;
use sqlbuild_analysis::assembly::analysis_session::models::{
    DynamicFamily, RelationTables, SessionRequest,
};
use sqlbuild_cache::project_reuse::types::ImageSections;
use sqlbuild_discovery::header_changes::types::HeaderKeys;
use sqlbuild_rules::engine::main::retained_request::retained_request;
use sqlbuild_rules::models::{EvaluateRequest, RetainedRows};

/// Whether edits that report or raise errors compile as deltas; until then they fall back.
pub(crate) const ERRORS_ON_DELTA_PATH: bool = true;

/// What one model contributes to the partial-check reasons, apart from its dependencies.
#[derive(Clone, Debug, Default, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub(crate) struct ModelCoverage {
    pub(crate) name: String,
    /// The model opts out of SQL analysis.
    pub(crate) disabled: bool,
    /// The model has a binding error, which makes every model reading it partial.
    pub(crate) blocked: bool,
    /// Its own reasons, sorted; those from invalid dependencies are derived.
    pub(crate) partial: Vec<String>,
}

impl ModelCoverage {
    /// Whether the model adds anything to the reasons.
    pub(crate) fn notable(&self) -> bool {
        self.disabled || self.blocked || !self.partial.is_empty()
    }
}

/// A stored compile's built-in rules request, as decoded for a delta compile.
#[derive(Clone, Debug)]
pub(crate) struct BaseRules {
    pub(crate) request: EvaluateRequest,
    /// Each model's payload digest, which keys its cached findings, in model order.
    pub(crate) digests: Vec<String>,
}

impl BaseRules {
    /// The rows a compile retained, decoded.
    pub(crate) fn decoded(retained: &RetainedRows) -> Option<Self> {
        Some(Self {
            request: retained_request(retained)?,
            digests: retained.digests.clone(),
        })
    }
}

/// A stored rules request, decoding on its own thread or decoded already.
#[derive(Debug)]
pub(crate) enum PendingRules {
    Decoding(std::thread::JoinHandle<Option<BaseRules>>),
    Ready(Box<BaseRules>),
}

impl PendingRules {
    /// The decoded request, or `None` when it could not be decoded.
    pub(crate) fn resolved(self) -> Option<BaseRules> {
        match self {
            Self::Decoding(handle) => {
                let Ok(rules) = handle.join() else {
                    return None;
                };
                rules
            }
            Self::Ready(rules) => Some(*rules),
        }
    }
}

/// The facts a full compile leaves for its project image beyond its analysis record.
#[derive(Debug, Default)]
pub(crate) struct ImageCapture {
    /// The sources functions and audits read, which a delta compile always keeps.
    pub(crate) pinned_sources: BTreeSet<String>,
    /// The sources each SQL test file reads, which a delta compile keeps when it reruns it.
    pub(crate) test_sources: BTreeMap<String, BTreeSet<String>>,
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
    pub(crate) header_keys: BTreeMap<String, HeaderKeys>,
    /// The audit factories each model file's header attaches, for files attaching any.
    pub(crate) audit_references: BTreeMap<String, Vec<String>>,
    /// Each model file's SQL lint cache key, in project model order.
    pub(crate) lint_model_keys: Option<Vec<(String, String)>>,
    /// Each other SQL file's lint cache key, in walk order.
    pub(crate) lint_file_keys: Option<Vec<(String, Option<String>)>>,
    /// The closed shape each model published for semantic checks, in publication order.
    pub(crate) model_shapes: Option<Vec<ModelShape>>,
    /// The notable semantic coverage facts of every model, when semantic checks reported them.
    pub(crate) coverage: Option<Vec<ModelCoverage>>,
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
    /// Every model file of the whole project, which path defaults are matched against.
    pub(crate) project_model_paths: Vec<String>,
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
    /// The whole project's notable semantic coverage facts, as the image recorded them.
    pub(crate) coverage: Option<Vec<ModelCoverage>>,
    /// Every project model in project order, with the models it reads.
    pub(crate) coverage_order: Vec<(String, Vec<String>)>,
    /// The audit factories each model file's header attaches, for files attaching any.
    pub(crate) audit_references: BTreeMap<String, Vec<String>>,
}

static CAPTURE: Mutex<Option<ImageCapture>> = Mutex::new(None);
static INJECTION: Mutex<Option<Arc<DeltaInjection>>> = Mutex::new(None);

/// Why the running delta compile cannot continue, once something ruled it out.
static UNSUPPORTED: Mutex<Option<String>> = Mutex::new(None);
static PENDING_IMAGE: Mutex<Option<ImageSections>> = Mutex::new(None);
static RECORD_MERGE: Mutex<Option<RecordMerge>> = Mutex::new(None);

fn locked<T>(slot: &Mutex<T>) -> MutexGuard<'_, T> {
    slot.lock().unwrap_or_else(PoisonError::into_inner)
}

/// Start capturing image facts for the compile about to run.
pub(crate) fn start_capture() {
    *locked(&CAPTURE) = Some(ImageCapture::default());
}

/// Stop capturing without keeping anything, for a project that turns delta compiles off.
pub(crate) fn stop_capture() {
    *locked(&CAPTURE) = None;
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

/// Record sources a resource other than a model reads, when a capture is running.
pub(crate) fn record_source_reads<'a>(names: impl IntoIterator<Item = &'a str>) {
    capture(|capture| {
        capture
            .pinned_sources
            .extend(names.into_iter().map(str::to_owned));
    });
}

/// Record sources an SQL test file reads, when a capture is running.
pub(crate) fn record_test_source_reads<'a>(
    relative_path: &str,
    names: impl IntoIterator<Item = &'a str>,
) {
    capture(|capture| {
        capture
            .test_sources
            .entry(relative_path.replace('\\', "/"))
            .or_default()
            .extend(names.into_iter().map(str::to_owned));
    });
}

/// Mark the running capture as unusable as a delta base.
pub(crate) fn capture_unsupported(reason: &str) {
    capture(|capture| {
        if capture.unsupported.is_none() {
            capture.unsupported = Some(reason.to_owned());
        }
    });
}

/// Run `body` with `injection` visible to the rerun stages; returns it unless still held.
pub(crate) fn with_injection<T>(
    injection: DeltaInjection,
    body: impl FnOnce() -> T,
) -> (T, Option<DeltaInjection>) {
    *locked(&INJECTION) = Some(Arc::new(injection));
    let result: T = body();
    let injection: Option<Arc<DeltaInjection>> = locked(&INJECTION).take();
    (
        result,
        injection.and_then(|injection| {
            let Ok(injection) = Arc::try_unwrap(injection) else {
                return None;
            };
            Some(injection)
        }),
    )
}

/// The running delta compile's injection, if any.
pub(crate) fn injection() -> Option<Arc<DeltaInjection>> {
    locked(&INJECTION).clone()
}

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
    let errors_on_delta_path: bool = ERRORS_ON_DELTA_PATH;
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

/// Give a delta's analysis session the whole project's relation facts and analysis order.
pub(crate) fn inject_relations(mut request: SessionRequest) -> pyo3::PyResult<SessionRequest> {
    let Some(injection) = injection() else {
        return Ok(request);
    };
    let relations: &RelationTables = &injection.relations;
    request.forced_order = Some((relations.dependency_ordered, relations.cyclic));
    request.retain_relations = true;
    let analysed: BTreeSet<&str> = request
        .models
        .iter()
        .map(|model| model.name.as_str())
        .collect();
    let rerun: BTreeSet<&str> = analysed
        .iter()
        .copied()
        .chain(injection.rerun_names.iter().map(String::as_str))
        .collect();
    request.dynamic_families_by_table = injected_families(
        &request.dynamic_families_by_table,
        &relations.families,
        &rerun,
    )?;
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
    Ok(request)
}

/// The stored compile's dynamic column families, when no rerun model changed its own.
fn injected_families(
    current: &[(String, Vec<DynamicFamily>)],
    stored: &[(String, Vec<DynamicFamily>)],
    rerun: &BTreeSet<&str>,
) -> pyo3::PyResult<Vec<(String, Vec<DynamicFamily>)>> {
    let families_of = |table: &[(String, Vec<DynamicFamily>)], name: &str| {
        table
            .iter()
            .find(|(table, _)| table == name)
            .map(|(_, families)| families.clone())
    };
    let changed: bool = current
        .iter()
        .any(|(name, _)| !rerun.contains(name.as_str()))
        || rerun
            .iter()
            .any(|name| families_of(current, name) != families_of(stored, name));
    if changed {
        return Err(delta_unsupported(
            "a model's dynamic column families changed",
        ));
    }
    Ok(stored.to_vec())
}

/// What a delta compile's reuse record keeps of the stored compile it patched.
#[derive(Debug, Default)]
pub(crate) struct RecordMerge {
    /// Each stored artifact's stamp, verified by the reuse check, kept unless the delta wrote it.
    pub(crate) kept: Vec<sqlbuild_cache::project_snapshot::models::PathStamp>,
    /// The template environment names the stored compile read.
    pub(crate) environment_names: Vec<String>,
    /// The module files the stored compile depended on, such as those behind stored macro calls.
    pub(crate) module_paths: Vec<String>,
}

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

/// Run a capture hook; a failure only rules the compile out as a delta base.
pub(crate) fn guarded(hook: impl FnOnce() -> PyResult<()>) -> PyResult<()> {
    if !capturing() {
        return Ok(());
    }
    if let Err(error) = hook() {
        capture_unsupported(&format!("an image fact could not be recorded: {error}"));
    }
    Ok(())
}
