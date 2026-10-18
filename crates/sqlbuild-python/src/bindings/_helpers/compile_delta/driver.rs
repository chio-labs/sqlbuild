//! Compile only the changed models and SQL tests, patching the stored compile's image and
//! report; anything this cannot reproduce exactly falls back to a full compile.

use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::path::PathBuf;

use pyo3::prelude::{Bound, Py, PyAny, PyAnyMethods, PyErr, PyResult, Python};
use pyo3::types::{PyString, PyStringMethods};
use sqlbuild_cache::project_reuse::main::read_delta_base::{read_delta_base, read_delta_output};
use sqlbuild_cache::project_reuse::models::{
    DeltaBase, DeltaCandidate, ImageSections, ProjectFileChanges,
};

use crate::bindings::_helpers::compile_command::reuse_recording::RecordedCompileOutput;
use crate::bindings::_helpers::compile_delta::context::{
    CapturedDiagnostic, CapturedTest, DeltaInjection, ImageCapture, RecordMerge, start_capture,
    take_capture, take_delta_unsupported, with_injection,
};
use crate::bindings::_helpers::compile_delta::header_keys::{
    HeaderChange, custom_rule_reads, header_change,
};
use crate::bindings::_helpers::compile_delta::image::{ImageRelations, ProjectImage};
use crate::bindings::_helpers::compile_delta::splice::{SpliceScope, spliced_report};
use crate::bindings::_helpers::compile_driver::command::{PhasesOutcome, unrecorded_compile};
use crate::bindings::_helpers::compile_outputs::reuse::NativeReuseAttempt;
use crate::bindings::_helpers::records::fields::field as native_field;

/// Set to `1` to always compile the whole project.
pub(crate) const DELTA_DISABLE_ENV_VAR: &str = "SQLBUILD_DISABLE_DELTA_COMPILE";
/// Set to `1` to run each delta compile beside a full compile and fail on any difference.
pub(crate) const DELTA_VERIFY_ENV_VAR: &str = "SQLBUILD_VERIFY_DELTA_COMPILE";
const ENABLED_VALUE: &str = "1";
/// Rerunning more models than this, or this share of the project, compiles the whole project.
const MAX_RERUN_MODELS: usize = 500;
const MAX_RERUN_PERCENT: usize = 5;
/// How many times a changed relation shape may pull its dependents into the delta.
const MAX_ROUNDS: usize = 4;
const MODELS_ROOT: &str = "models/";
const TESTS_ROOT: &str = "tests/";
const SQL_SUFFIX: &str = ".sql";
/// Under verification, the delta's own report is kept here for inspection.
const VERIFY_REPORT_DIRECTORY: &str = "target/cache/compiler-native-v1";
const VERIFY_REPORT_FILE: &str = "delta-report.out";

/// Whether the environment turns `name` on.
pub(crate) fn env_enabled(name: &str) -> bool {
    std::env::var(name).is_ok_and(|value| value == ENABLED_VALUE)
}

/// Whether delta compiles, and so project images, are on for this process.
pub(crate) fn delta_enabled() -> bool {
    !env_enabled(DELTA_DISABLE_ENV_VAR)
}

/// A delta compile that finished, ready to be stored and printed or compared.
pub(crate) struct Finished<'py> {
    pub(crate) request: Bound<'py, PyAny>,
    pub(crate) stdout: String,
    pub(crate) stderr_lines: Vec<Py<PyString>>,
    pub(crate) phases: PhasesOutcome<'py>,
    pub(crate) image: Option<ImageSections>,
    pub(crate) merge: RecordMerge,
    pub(crate) changed_files: usize,
    pub(crate) rerun_models: usize,
}

/// What one delta attempt came to.
pub(crate) enum DeltaOutcome<'py> {
    /// The delta cannot reproduce this compile; the reason is for diagnostics only.
    Fallback(String),
    /// The compile stopped on an error from a changed file, exactly as a full compile would.
    Raised(PyErr),
    Finished(Box<Finished<'py>>),
}

fn fallback<'py>(reason: impl Into<String>) -> PyResult<DeltaOutcome<'py>> {
    Ok(DeltaOutcome::Fallback(reason.into()))
}

/// Whether the invocation asks for anything a delta compile does not reproduce.
fn ineligible(request: &Bound<'_, PyAny>) -> PyResult<Option<&'static str>> {
    let empty = |name: &str| -> PyResult<bool> {
        let value: Bound<'_, PyAny> = native_field(request, name)?;
        Ok(value.is_none() || !value.is_truthy()?)
    };
    for (name, reason) in [
        ("select", "a selection was given"),
        ("exclude", "an exclusion was given"),
        ("dag_path", "a DAG artifact was requested"),
        ("manifest", "a manifest was requested"),
        ("defer_to", "deferral was requested"),
        ("no_sql_validation", "SQL validation is off"),
    ] {
        if !empty(name)? {
            return Ok(Some(reason));
        }
    }
    let lineage: Bound<'_, PyAny> = native_field(request, "lineage_mode")?;
    if !lineage.is_none() && lineage.getattr("value")?.str()?.to_str()? != "fast" {
        return Ok(Some("rich lineage was requested"));
    }
    let flags: Bound<'_, PyAny> = native_field(request, "profile_flags")?;
    for name in [
        "skip_discovery_sql_analysis",
        "skip_column_inference",
        "skip_contracts",
        "skip_write",
    ] {
        if native_field(&flags, name)?.is_truthy()? {
            return Ok(Some("a profiling flag was given"));
        }
    }
    Ok(None)
}

/// A path the delta may recompile: an SQL file in a resource tree, not a declaration tree.
fn resource_sql(path: &str, root: &str) -> bool {
    path.starts_with(root)
        && path.ends_with(SQL_SUFFIX)
        && !path.split('/').any(|part| part.starts_with('_'))
}

/// The stored compile's inputs and image, read from the attempt's slot; its report is read
/// only once the delta has run.
struct Base {
    store_path: PathBuf,
    stored: DeltaBase,
    image: ProjectImage,
}

/// The project files the reuse check found changed, and the slot it checked.
fn changes_of(
    attempt: &Bound<'_, PyAny>,
) -> PyResult<Result<(ProjectFileChanges, PathBuf), String>> {
    let native: Bound<'_, PyAny> = native_field(attempt, "native")?;
    let Ok(native) = native.cast::<NativeReuseAttempt>() else {
        return Ok(Err("the reuse check did not run".to_owned()));
    };
    let (delta, store_path): (DeltaCandidate, PathBuf) = native
        .get()
        .with_attempt(|attempt| (attempt.delta.clone(), attempt.store_path.clone()))?;
    Ok(match delta {
        DeltaCandidate::Files(changes) => Ok((changes, store_path)),
        DeltaCandidate::Unavailable(reason) => Err(reason.to_owned()),
    })
}

fn base_of(store_path: PathBuf) -> Result<Base, String> {
    let Some(stored) = read_delta_base(&store_path) else {
        return Err("the stored compile has no project image".to_owned());
    };
    let Some(image) = ProjectImage::decode(&stored.image) else {
        return Err("the project image cannot be read".to_owned());
    };
    Ok(Base {
        store_path,
        stored,
        image,
    })
}

/// The rerun set: models and SQL tests, with every path and name the delta recompiles.
#[derive(Clone, Debug, Default)]
struct Rerun {
    changed: BTreeSet<String>,
    models: BTreeSet<String>,
    model_paths: BTreeSet<String>,
    test_paths: BTreeSet<String>,
    tests: BTreeSet<String>,
}

impl Rerun {
    fn with_tests(mut self, image: &ProjectImage, changed_tests: &BTreeSet<String>) -> Self {
        self.test_paths = changed_tests.clone();
        let test_files: BTreeSet<&str> = image
            .tests
            .iter()
            .map(|test| test.relative_path.as_str())
            .collect();
        for diagnostic in &image.diagnostics {
            for path in &diagnostic.paths {
                if test_files.contains(path.as_str()) {
                    self.test_paths.insert(path.clone());
                }
            }
        }
        for test in &image.tests {
            if test.chain.iter().any(|name| self.models.contains(name)) {
                self.test_paths.insert(test.relative_path.clone());
            }
        }
        self.tests = image
            .tests
            .iter()
            .filter(|test| self.test_paths.contains(&test.relative_path))
            .map(|test| test.key.clone())
            .collect();
        self
    }

    fn names(&self) -> BTreeSet<String> {
        let mut names: BTreeSet<String> = self.models.clone();
        names.extend(self.model_paths.iter().cloned());
        names.extend(self.tests.iter().cloned());
        names.extend(self.test_paths.iter().cloned());
        names
    }

    fn owns(&self, diagnostic: &CapturedDiagnostic) -> bool {
        diagnostic
            .resource_name
            .as_ref()
            .is_some_and(|name| self.models.contains(name) || self.tests.contains(name))
            || diagnostic
                .paths
                .iter()
                .any(|path| self.model_paths.contains(path) || self.test_paths.contains(path))
    }
}

fn injection_for(base: &Base, rerun: &Rerun, project_dir: PathBuf) -> DeltaInjection {
    let image: &ProjectImage = &base.image;
    DeltaInjection {
        project_dir,
        model_paths: rerun.model_paths.clone(),
        test_paths: rerun.test_paths.clone(),
        rerun_names: rerun.names(),
        source_paths: image
            .models
            .iter()
            .map(|model| model.relative_path.clone())
            .chain(image.tests.iter().map(|test| test.relative_path.clone()))
            .collect(),
        model_names: image
            .models
            .iter()
            .map(|model| model.name.clone())
            .collect(),
        relations: (&image.relations).into(),
        rules: image.rules.clone(),
        fact_digests: image.fact_digests.iter().cloned().collect(),
        model_subjects: image.model_subjects.clone(),
        text_models: image.text_models.clone().unwrap_or_default(),
        model_shapes: image.model_shapes.clone(),
        changed_paths: rerun.changed.clone(),
        lint_model_keys: image.lint_model_keys.clone(),
        lint_file_keys: image.lint_file_keys.clone(),
    }
}

/// The relation facts of `name` that its dependents' analysis reads.
fn shape_of(relations: &ImageRelations, name: &str) -> [Option<Vec<(String, String)>>; 3] {
    let find = |table: &[(String, Vec<(String, String)>)]| {
        table
            .iter()
            .find(|(relation, _)| relation == name)
            .map(|(_, shape)| shape.clone())
    };
    [
        find(&relations.types),
        find(&relations.nullability),
        find(&relations.complete),
    ]
}

/// `base`'s rows with each of `fresh`'s rows replacing the one of its name, new names appended.
fn merged_rows(
    base: &mut Vec<(String, Vec<(String, String)>)>,
    fresh: Vec<(String, Vec<(String, String)>)>,
) {
    let mut positions: HashMap<String, usize> = base
        .iter()
        .enumerate()
        .map(|(index, (name, _))| (name.clone(), index))
        .collect();
    for (name, shape) in fresh {
        match positions.get(&name) {
            Some(index) => base[*index].1 = shape,
            None => {
                positions.insert(name.clone(), base.len());
                base.push((name, shape));
            }
        }
    }
}

/// One restricted compile of `rerun`, with what it captured.
struct Round<'py> {
    request: Bound<'py, PyAny>,
    output: Bound<'py, PyAny>,
    phases: PhasesOutcome<'py>,
    capture: ImageCapture,
}

enum RoundOutcome<'py> {
    Ran(Box<Round<'py>>),
    Stop(DeltaOutcome<'py>),
}

fn round<'py>(
    request: &Bound<'py, PyAny>,
    attempt: &Bound<'py, PyAny>,
    (base, rerun): (&Base, &Rerun),
) -> PyResult<RoundOutcome<'py>> {
    let project_dir: PathBuf = native_field(attempt, "project_dir")?.extract()?;
    start_capture();
    let ran = with_injection(injection_for(base, rerun, project_dir), || {
        unrecorded_compile(request, attempt)
    });
    let unsupported: Option<String> = take_delta_unsupported();
    let capture: Option<ImageCapture> = take_capture();
    if let Some(reason) = unsupported {
        return Ok(RoundOutcome::Stop(DeltaOutcome::Fallback(reason)));
    }
    let (request, output, phases) = match ran {
        Ok(ran) => ran,
        Err(error) => {
            return Ok(RoundOutcome::Stop(DeltaOutcome::Fallback(format!(
                "the delta compile failed: {error}"
            ))));
        }
    };
    let phases: PhasesOutcome<'py> = match phases {
        Ok(phases) => phases,
        Err(error) => {
            let message: String = error.to_string();
            let owned: bool = rerun
                .model_paths
                .iter()
                .chain(&rerun.test_paths)
                .any(|path| message.contains(path.as_str()));
            return Ok(RoundOutcome::Stop(if owned {
                DeltaOutcome::Raised(error)
            } else {
                DeltaOutcome::Fallback(format!("the delta compile raised: {message}"))
            }));
        }
    };
    let Some(capture) = capture else {
        return Ok(RoundOutcome::Stop(DeltaOutcome::Fallback(
            "the delta compile captured nothing".to_owned(),
        )));
    };
    if let Some(reason) = &capture.unsupported {
        return Ok(RoundOutcome::Stop(DeltaOutcome::Fallback(reason.clone())));
    }
    Ok(RoundOutcome::Ran(Box::new(Round {
        request,
        output,
        phases,
        capture,
    })))
}

/// Compile the changed files against the stored compile, or say why that is not possible.
pub(crate) fn run<'py>(
    request: &Bound<'py, PyAny>,
    attempt: &Bound<'py, PyAny>,
) -> PyResult<DeltaOutcome<'py>> {
    if !delta_enabled() {
        return fallback("delta compiles are off");
    }
    if let Some(reason) = ineligible(request)? {
        return fallback(reason);
    }
    let started: std::time::Instant = std::time::Instant::now();
    let (changes, store_path): (ProjectFileChanges, PathBuf) = match changes_of(attempt)? {
        Ok(found) => found,
        Err(reason) => return fallback(reason),
    };
    if !changes.added.is_empty() || !changes.removed.is_empty() {
        return fallback("files were added or removed");
    }
    if changes.changed.is_empty() {
        return fallback("no project file changed");
    }
    if let Some(path) = changes
        .changed
        .iter()
        .find(|path| !resource_sql(path, MODELS_ROOT) && !resource_sql(path, TESTS_ROOT))
    {
        return fallback(format!("{path} is not a model or SQL test file"));
    }
    let base: Base = match base_of(store_path) {
        Ok(base) => base,
        Err(reason) => return fallback(reason),
    };
    let json_output: bool = native_field(request, "json_output")?.is_truthy()?;
    if base.image.json_output != json_output {
        return fallback("the stored compile has the other output format");
    }
    let model_by_path: HashMap<&str, &str> = base
        .image
        .models
        .iter()
        .map(|model| (model.relative_path.as_str(), model.name.as_str()))
        .collect();
    let test_files: BTreeSet<&str> = base
        .image
        .tests
        .iter()
        .map(|test| test.relative_path.as_str())
        .collect();
    let mut rerun: Rerun = Rerun {
        changed: changes.changed.iter().cloned().collect(),
        ..Rerun::default()
    };
    let mut changed_tests: BTreeSet<String> = BTreeSet::new();
    for path in &changes.changed {
        if resource_sql(path, MODELS_ROOT)
            && let Some(name) = model_by_path.get(path.as_str())
        {
            rerun.models.insert((*name).to_owned());
            rerun.model_paths.insert(path.clone());
        } else if resource_sql(path, TESTS_ROOT) && test_files.contains(path.as_str()) {
            changed_tests.insert(path.clone());
        } else {
            return fallback(format!("{path} is not a model or SQL test file"));
        }
    }
    let project_dir: PathBuf = native_field(attempt, "project_dir")?.extract()?;
    for path in &rerun.model_paths {
        let name: &str = model_by_path
            .get(path.as_str())
            .copied()
            .unwrap_or_default();
        match header_change(&project_dir, path, base.image.header_keys.get(path)) {
            HeaderChange::Unchanged | HeaderChange::Unparsed => {}
            HeaderChange::Unsupported(reason) => return fallback(reason),
            HeaderChange::Patched(keys) => {
                if base.image.model_subjects.is_some() && keys.contains("materialized") {
                    return fallback("custom rules select models by their materialization");
                }
                if let Some(reason) =
                    custom_rule_reads(&base.image.fact_digests, (path, name), &keys)
                {
                    return fallback(reason);
                }
            }
        }
    }
    let limit: usize = MAX_RERUN_MODELS.max(base.image.models.len() * MAX_RERUN_PERCENT / 100);
    let mut last: Option<Round<'py>> = None;
    for _ in 0..MAX_ROUNDS {
        if rerun.models.len() > limit {
            return fallback("too many models would compile again");
        }
        rerun = rerun.with_tests(&base.image, &changed_tests);
        trace(request.py(), "delta base read", started)?;
        let ran: Round<'py> = match round(request, attempt, (&base, &rerun))? {
            RoundOutcome::Ran(ran) => *ran,
            RoundOutcome::Stop(outcome) => return Ok(outcome),
        };
        if rerun.models.is_empty() {
            last = Some(ran);
            break;
        }
        let Some(relations) = ran.capture.relations.clone() else {
            return fallback("the delta compile analysed no models");
        };
        let relations: ImageRelations = relations.into();
        if relations.cyclic != base.image.relations.cyclic
            || relations.dependency_ordered != base.image.relations.dependency_ordered
        {
            return fallback("the project's analysis order changed");
        }
        for model in &ran.capture.models {
            let stored = base
                .image
                .models
                .iter()
                .find(|stored| stored.name == model.name);
            if stored != Some(model) {
                return fallback(format!("{} changed its references", model.name));
            }
        }
        for path in &rerun.model_paths {
            if ran.capture.usages.get(path) != base.image.usages.get(path) {
                return fallback(format!("{path} changed the declarations it uses"));
            }
        }
        let reshaped: BTreeSet<String> = rerun
            .models
            .iter()
            .filter(|name| shape_of(&relations, name) != shape_of(&base.image.relations, name))
            .cloned()
            .collect();
        let dependents: BTreeSet<String> = base.image.dependents(&reshaped);
        let added: Vec<String> = dependents
            .into_iter()
            .filter(|name| !rerun.models.contains(name))
            .collect();
        last = Some(ran);
        if added.is_empty() {
            break;
        }
        for name in added {
            if let Some(model) = base.image.models.iter().find(|model| model.name == name) {
                rerun.model_paths.insert(model.relative_path.clone());
            }
            rerun.models.insert(name);
        }
        last = None;
    }
    let Some(ran) = last else {
        return fallback("changed shapes reach too far");
    };
    trace(request.py(), "delta rounds", started)?;
    let outcome = finished(ran, &base, &rerun, changes.changed.len());
    trace(request.py(), "delta report", started)?;
    outcome
}

/// Log how long the delta has run, for profiling.
pub(crate) fn trace(py: Python<'_>, phase: &str, started: std::time::Instant) -> PyResult<()> {
    let milliseconds: u128 = started.elapsed().as_millis();
    py.import("logging")?
        .getattr("getLogger")?
        .call1(("sqlbuild.compile.delta",))?
        .call_method1("debug", ("%s after %d ms", phase, milliseconds))?;
    Ok(())
}

/// Every diagnostic not owned by the rerun set, which the delta must leave as it was.
fn unowned<'a>(rerun: &Rerun, diagnostics: &'a [CapturedDiagnostic]) -> Vec<&'a str> {
    diagnostics
        .iter()
        .filter(|diagnostic| !rerun.owns(diagnostic))
        .map(|diagnostic| diagnostic.json.as_str())
        .collect()
}

fn finished<'py>(
    ran: Round<'py>,
    base: &Base,
    rerun: &Rerun,
    changed_files: usize,
) -> PyResult<DeltaOutcome<'py>> {
    let py: Python<'py> = ran.request.py();
    if unowned(rerun, &base.image.diagnostics) != unowned(rerun, &ran.capture.diagnostics) {
        return fallback("diagnostics outside the changed files differ");
    }
    let recorded: Bound<'py, PyAny> = ran.output.getattr("stdout")?;
    if recorded.is_none() {
        return fallback("the delta compile recorded no report");
    }
    let delta_stdout: String = recorded.extract()?;
    let Some(stored_output) = read_delta_output(&base.store_path, &base.stored) else {
        return fallback("the stored report changed");
    };
    if env_enabled(DELTA_VERIFY_ENV_VAR) {
        let project_dir: PathBuf = native_field(&ran.request, "project_dir")?.extract()?;
        let directory: PathBuf = project_dir.join(VERIFY_REPORT_DIRECTORY);
        let _ = std::fs::create_dir_all(&directory);
        let _ = std::fs::write(directory.join(VERIFY_REPORT_FILE), &delta_stdout);
    }
    let stdout: String = if base.image.json_output {
        let scope: SpliceScope<'_> = SpliceScope {
            models: &rerun.models,
            tests: &rerun.tests,
        };
        match spliced_report(&stored_output.stdout, &delta_stdout, &scope) {
            Ok(stdout) => stdout,
            Err(reason) => return fallback(reason),
        }
    } else {
        delta_stdout
    };
    let stderr_lines: Vec<Py<PyString>> = ran.output.getattr("stderr_lines")?.extract()?;
    let image: Option<ImageSections> = patched_image(&base.image, rerun, ran.capture).encode().ok();
    let merge: RecordMerge = RecordMerge {
        kept: base
            .stored
            .inputs
            .target_files
            .iter()
            .map(|stamp| (stamp.relative_path.clone(), stamp.size, stamp.mtime_ns))
            .collect(),
        environment_names: base.image.environment_names.clone(),
    };
    let _ = py;
    Ok(DeltaOutcome::Finished(Box::new(Finished {
        request: ran.request,
        stdout,
        stderr_lines,
        phases: ran.phases,
        image,
        merge,
        changed_files,
        rerun_models: rerun.models.len(),
    })))
}

/// The stored image with the rerun models' and tests' facts replaced by the delta's.
fn patched_image(base: &ProjectImage, rerun: &Rerun, capture: ImageCapture) -> ProjectImage {
    let mut image: ProjectImage = base.clone();
    let fresh_models: HashMap<String, _> = capture
        .models
        .into_iter()
        .map(|model| (model.name.clone(), model))
        .collect();
    for model in &mut image.models {
        if let Some(fresh) = fresh_models.get(&model.name) {
            *model = fresh.clone();
        }
    }
    image.usages.extend(capture.usages);
    let mut fresh_tests: HashMap<String, CapturedTest> = capture
        .test_chains
        .into_iter()
        .map(|test| (test.key.clone(), test))
        .collect();
    for test in &mut image.tests {
        if rerun.tests.contains(&test.key)
            && let Some(fresh) = fresh_tests.remove(&test.key)
        {
            *test = fresh;
        }
    }
    if let Some(relations) = capture.relations {
        let fresh: ImageRelations = relations.into();
        merged_rows(&mut image.relations.types, fresh.types);
        merged_rows(&mut image.relations.nullability, fresh.nullability);
        merged_rows(&mut image.relations.complete, fresh.complete);
        merged_rows(&mut image.relations.schemas, fresh.schemas);
        let mut legacy: BTreeSet<String> = image.relations.legacy_models.iter().cloned().collect();
        for name in &rerun.models {
            legacy.remove(name);
        }
        legacy.extend(fresh.legacy_models);
        image.relations.legacy_models = legacy.into_iter().collect();
    }
    let mut digests: BTreeMap<Vec<String>, String> = image.fact_digests.into_iter().collect();
    digests.extend(capture.fact_digests);
    image.fact_digests = digests.into_iter().collect();
    image.diagnostics = capture.diagnostics;
    if capture.text_models.is_some() {
        image.text_models = capture.text_models;
    }
    image.rules = capture.rules.map(|rules| rules.retained);
    if let Some(shapes) = capture.model_shapes {
        image.model_shapes = shapes;
    }
    image.header_keys.extend(capture.header_keys);
    image.lint_model_keys = capture.lint_model_keys;
    image.lint_file_keys = capture.lint_file_keys;
    image
}

/// Store and print a finished delta compile; returns its exit code.
pub(crate) fn commit(finished: Finished<'_>, attempt: &Bound<'_, PyAny>) -> PyResult<i64> {
    let py: Python<'_> = attempt.py();
    let Finished {
        request,
        stdout,
        stderr_lines,
        phases,
        image,
        merge,
        ..
    } = finished;
    let report: &str = stdout.strip_suffix('\n').unwrap_or(&stdout);
    let output: Bound<'_, PyAny> = Bound::new(
        py,
        RecordedCompileOutput::recorded(
            stderr_lines,
            PyString::new(py, &format!("{report}\n")).unbind(),
        ),
    )?
    .into_any();
    crate::bindings::_helpers::compile_delta::context::set_pending_image(image);
    crate::bindings::_helpers::compile_delta::context::set_record_merge(Some(merge));
    crate::bindings::_helpers::compile_driver::command::store_and_print(
        (&request, attempt),
        &output,
        phases,
    )
}
