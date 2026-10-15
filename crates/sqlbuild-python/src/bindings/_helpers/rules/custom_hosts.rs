//! Run planned custom-rule invocations across isolated host processes and merge their results.

use std::collections::BTreeSet;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::mpsc::{Receiver, Sender, channel};

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyErr, PyResult, Python};
use pyo3::types::{PyBytes, PyBytesMethods, PyDict, PyDictMethods, PyTuple};
use serde_json::{Map, Value, json};
use sqlbuild_rules::custom_host_pool::constants::{CGROUP_ROOT, HOST_TIMEOUT_MILLIS, PROC_CGROUP};
use sqlbuild_rules::custom_host_pool::main::available_cores::available_cores;
use sqlbuild_rules::custom_host_pool::main::decode_host_response::decode_host_response;
use sqlbuild_rules::custom_host_pool::main::host_count::host_count;
use sqlbuild_rules::custom_host_pool::main::merge_host_slices::merge_host_slices;
use sqlbuild_rules::custom_host_pool::main::partition_host_plan::partition_host_plan;
use sqlbuild_rules::custom_host_pool::main::planned_invocations::planned_invocations;
use sqlbuild_rules::custom_host_pool::main::without_codes::without_codes;
use sqlbuild_rules::custom_host_pool::models::{HostRuleSubject, HostRun, HostSlice};
use sqlbuild_rules::custom_host_pool::types::{HostInvocation, HostPlan};
use sqlbuild_rules::engine::main::custom_host::run_custom_host_json;

use crate::bindings::_helpers::compile_driver::python_calls::imported;

const NATIVE_MODULE: &str = "sqlbuild._native";
const RULES_CONSTANTS_MODULE: &str = "sqlbuild.rule_engine.constants";
const RULES_ERRORS_MODULE: &str = "sqlbuild.rule_engine.exceptions";
const COMPILE_MODELS_MODULE: &str = "sqlbuild.compiler.compile.models";
const HOST_INPUTS: [&str; 3] = ["target", "rules-cache", "host-inputs"];
/// The model fields hosts decode; every other model field is dropped from their payload.
const PAYLOAD_MODEL_FIELDS: [&str; 18] = [
    "key",
    "deps",
    "name",
    "relative_path",
    "query_sql",
    "config",
    "destination",
    "schema_entry",
    "inferred_columns",
    "fast_lineage_has_star",
    "fast_lineage_star_resolved",
    "authored_sql",
    "extract_implicit_alias_columns",
    "enum_declarations",
    "constant_declarations",
    "binding_validated",
    "dynamic_column_contract",
    "rejected_sql_analysis_opt_out",
];

static INPUT_COUNTER: AtomicUsize = AtomicUsize::new(0);

/// What every host of one run is told, before its plan and cancellation marker are added.
pub(crate) struct HostRequest<'a, 'py> {
    pub(crate) project: &'a Bound<'py, PyAny>,
    pub(crate) config: &'a Bound<'py, PyAny>,
    pub(crate) project_dir: &'a Path,
    pub(crate) dialect: &'a str,
    pub(crate) rules: &'a [(String, HostRuleSubject)],
    pub(crate) model_paths: &'a [String],
    pub(crate) track_reads: bool,
    pub(crate) verify_determinism: bool,
}

/// One host's outcome: its slice, or the `RulesError` message it failed with.
type HostOutcome = Result<HostSlice, String>;
/// Whether a host finished, without its slice, so the waiter can cancel the rest.
type HostStatus = Result<(), String>;

/// Evaluate `plan` across host processes and merge their results in single-host order.
pub(crate) fn run_custom_hosts(
    py: Python<'_>,
    request: &HostRequest<'_, '_>,
    plan: &HostPlan,
) -> PyResult<HostRun> {
    let invocations: Vec<HostInvocation> =
        planned_invocations(plan, request.rules, request.model_paths);
    let plans: Vec<HostPlan> = if request.verify_determinism {
        vec![plan.clone()]
    } else {
        partition_host_plan(
            plan,
            &invocations,
            host_count(invocations.len(), cores(py)?),
        )
    };
    let input_dir: PathBuf = HOST_INPUTS
        .iter()
        .fold(request.project_dir.to_path_buf(), |path, part| {
            path.join(part)
        });
    std::fs::create_dir_all(&input_dir)?;
    let input_dir: PathBuf = input_dir.canonicalize()?;
    let stem: String = format!("project-{}", uuid_hex(py)?);
    let input_path: PathBuf = input_dir.join(format!("{stem}.pickle"));
    let abandoned: PathBuf = input_dir.join(format!(
        "{stem}{}",
        constant::<String>(py, "CUSTOM_HOST_ABANDONED_SUFFIX")?
    ));
    let mut payload: Map<String, Value> = Map::new();
    payload.insert("project_pickle_path".to_owned(), json!(text(&input_path)));
    payload.insert("abandoned_marker".to_owned(), json!(text(&abandoned)));
    payload.insert("parent_pid".to_owned(), json!(std::process::id()));
    payload.insert(
        "project_dir".to_owned(),
        json!(text(&request.project_dir.canonicalize()?)),
    );
    payload.insert("dialect".to_owned(), json!(request.dialect));
    payload.insert(
        "verify_determinism".to_owned(),
        json!(request.verify_determinism),
    );
    payload.insert("track_reads".to_owned(), json!(request.track_reads));
    let launch: Launch = Launch::new(py, payload)?;
    let responses: PyResult<Vec<HostSlice>> = run_partitions(
        py,
        (&launch, plan, &plans),
        &input_dir,
        (|| write_inputs(py, &input_path, request), &abandoned),
    );
    remove_file(&input_path);
    remove_file(&abandoned);
    Ok(merge_host_slices(responses?, &invocations))
}

/// The program, arguments and shared payload every host starts with.
struct Launch {
    program: String,
    arguments: Vec<String>,
    runtime_version: String,
    payload: Map<String, Value>,
}

impl Launch {
    fn new(py: Python<'_>, payload: Map<String, Value>) -> PyResult<Self> {
        Ok(Self {
            program: imported(py, "sys", "executable")?.extract()?,
            arguments: vec!["-m".to_owned(), constant(py, "CUSTOM_HOST_LAUNCH_MODULE")?],
            runtime_version: constant(py, "CUSTOM_HOST_RUNTIME_VERSION")?,
            payload,
        })
    }

    /// The `run_custom_host_json` request for one host's plan and optional cancellation marker.
    fn spec(&self, plan: &HostPlan, cancel_marker: Option<&Path>) -> String {
        let mut payload: Map<String, Value> = self.payload.clone();
        payload.insert("plan".to_owned(), json!(plan));
        if let Some(marker) = cancel_marker {
            payload.insert("cancel_marker".to_owned(), json!(text(marker)));
        }
        json!({
            "program": self.program,
            "arguments": self.arguments,
            "timeout_millis": HOST_TIMEOUT_MILLIS,
            "runtime_version": self.runtime_version,
            "payload": payload,
        })
        .to_string()
    }
}

/// Start hosts while the payload is written; failures and module state fall back to one host.
fn run_partitions<'py>(
    py: Python<'py>,
    (launch, plan, plans): (&Launch, &HostPlan, &[HostPlan]),
    input_dir: &Path,
    (write_inputs, abandoned): (impl FnOnce() -> PyResult<()>, &Path),
) -> PyResult<Vec<HostSlice>> {
    if plans.len() == 1 {
        let spec: String = launch.spec(plan, None);
        let outcomes: Vec<HostOutcome> =
            run_hosts(py, vec![spec], (write_inputs, abandoned), None)?;
        return outcomes
            .into_iter()
            .map(|outcome| outcome.map_err(|message| rules_error(py, message)))
            .collect();
    }
    let cancel_dir: PathBuf = unique_directory(input_dir, "hosts-")?;
    let marker: PathBuf = cancel_dir.join(constant::<String>(py, "CUSTOM_HOST_CANCELLED_MARKER")?);
    let specs: Vec<String> = plans
        .iter()
        .map(|partition| launch.spec(partition, Some(&marker)))
        .collect();
    let outcomes: PyResult<Vec<HostOutcome>> =
        run_hosts(py, specs, (write_inputs, abandoned), Some(&marker));
    let _removed: std::io::Result<()> = std::fs::remove_dir_all(&cancel_dir);
    let outcomes: Vec<HostOutcome> = outcomes?;
    if outcomes.iter().any(Result::is_err) {
        return single_host(py, launch, plan).map(|slice| vec![slice]);
    }
    let slices: Vec<HostSlice> = outcomes.into_iter().filter_map(Result::ok).collect();
    let stateful: BTreeSet<String> = slices
        .iter()
        .flat_map(|slice| slice.stateful.iter().cloned())
        .collect();
    if stateful.is_empty() {
        return Ok(slices);
    }
    let rerun_plan: HostPlan = plan
        .iter()
        .map(|(code, subjects)| {
            let subjects: Option<Vec<String>> = if stateful.contains(code) {
                subjects.clone()
            } else {
                Some(Vec::new())
            };
            (code.clone(), subjects)
        })
        .collect();
    let rerun: HostSlice = single_host(py, launch, &rerun_plan)?;
    let mut merged: Vec<HostSlice> = slices
        .into_iter()
        .map(|slice| without_codes(slice, &stateful))
        .collect();
    merged.push(rerun);
    Ok(merged)
}

/// Run one host for `plan` once the payload already exists.
fn single_host(py: Python<'_>, launch: &Launch, plan: &HostPlan) -> PyResult<HostSlice> {
    let spec: String = launch.spec(plan, None);
    py.detach(|| host_outcome(&spec))
        .map_err(|message| rules_error(py, message))
}

/// Run every host on its own thread while this thread publishes the payload they wait for.
fn run_hosts(
    py: Python<'_>,
    specs: Vec<String>,
    (write_inputs, abandoned): (impl FnOnce() -> PyResult<()>, &Path),
    cancel_marker: Option<&Path>,
) -> PyResult<Vec<HostOutcome>> {
    std::thread::scope(|scope| {
        let (sender, finished): (Sender<HostStatus>, Receiver<HostStatus>) = channel();
        let handles: Vec<_> = specs
            .into_iter()
            .map(|spec| {
                let sender: Sender<HostStatus> = sender.clone();
                scope.spawn(move || {
                    let outcome: HostOutcome = host_outcome(&spec);
                    let status: HostStatus = outcome.as_ref().map(drop).map_err(Clone::clone);
                    let _sent: Result<(), std::sync::mpsc::SendError<HostStatus>> =
                        sender.send(status);
                    outcome
                })
            })
            .collect();
        drop(sender);
        let published: PyResult<()> = write_inputs();
        if let Err(error) = published {
            if let Ok(()) = touch(abandoned) {
                py.detach(|| handles.into_iter().for_each(|handle| drop(handle.join())));
            }
            return Err(error);
        }
        let count: usize = handles.len();
        py.detach(move || {
            for _ in 0..count {
                match finished.recv() {
                    Ok(Ok(())) => {}
                    Ok(Err(_)) | Err(_) => {
                        if let Some(marker) = cancel_marker {
                            let _touched: std::io::Result<()> = touch(marker);
                        }
                        break;
                    }
                }
            }
            Ok(handles
                .into_iter()
                .map(|handle| {
                    handle
                        .join()
                        .unwrap_or_else(|_| Err("custom rule host thread panicked".to_owned()))
                })
                .collect())
        })
    })
}

/// One host run decoded, or the message `RulesError` reports for it.
fn host_outcome(spec: &str) -> HostOutcome {
    let response: String = run_custom_host_json(spec)?;
    let value: Value = serde_json::from_str(&response).map_err(|error| error.to_string())?;
    decode_host_response(&value)
}

/// Publish the pickled project and config atomically; hosts started earlier wait for it.
fn write_inputs(py: Python<'_>, path: &Path, request: &HostRequest<'_, '_>) -> PyResult<()> {
    let payload: Bound<'_, PyAny> = host_payload_project(request.project)?;
    let pickled: Bound<'_, PyAny> = imported(py, "pickle", "dumps")?
        .call1((PyTuple::new(py, [payload, request.config.clone()])?,))?;
    let bytes: &[u8] = pickled.cast::<PyBytes>()?.as_bytes();
    let parent: &Path = path.parent().unwrap_or(path);
    let partial: PathBuf = parent.join(format!(
        "writing-{}-{}.pickle",
        std::process::id(),
        INPUT_COUNTER.fetch_add(1, Ordering::Relaxed)
    ));
    if let Err(error) = std::fs::write(&partial, bytes) {
        remove_file(&partial);
        return Err(error.into());
    }
    std::fs::rename(&partial, path)?;
    Ok(())
}

/// The project hosts decode, without model state no rule fact reads.
fn host_payload_project<'py>(project: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let py: Python<'py> = project.py();
    let model_class: Bound<'py, PyAny> = imported(py, COMPILE_MODELS_MODULE, "CompiledModel")?;
    let mut models: Vec<Bound<'py, PyAny>> = Vec::new();
    for model in project.getattr("models")?.try_iter()? {
        let model: Bound<'py, PyAny> = model?;
        let fields: Bound<'py, PyDict> = PyDict::new(py);
        for name in PAYLOAD_MODEL_FIELDS {
            fields.set_item(name, model.getattr(name)?)?;
        }
        models.push(model_class.call((), Some(&fields))?);
    }
    let record: Bound<'py, PyAny> =
        imported(py, NATIVE_MODULE, "compiled_project_record")?.call1((project,))?;
    let options: Bound<'py, PyDict> = PyDict::new(py);
    options.set_item("models", PyTuple::new(py, models)?)?;
    options.set_item("native_project", py.None())?;
    imported(py, "dataclasses", "replace")?.call((record,), Some(&options))
}

/// Usable CPUs: the process CPU count capped by any cgroup CPU quota.
fn cores(py: Python<'_>) -> PyResult<usize> {
    let os: Bound<'_, PyAny> = py.import("os")?.into_any();
    let count: Option<usize> = if os.hasattr("process_cpu_count")? {
        os.call_method0("process_cpu_count")?.extract()?
    } else if os.hasattr("sched_getaffinity")? {
        Some(os.call_method1("sched_getaffinity", (0,))?.len()?)
    } else {
        os.call_method0("cpu_count")?.extract()?
    };
    Ok(available_cores(
        count.unwrap_or(1),
        (Path::new(CGROUP_ROOT), Path::new(PROC_CGROUP)),
    ))
}

fn constant<'py, T: pyo3::FromPyObject<'py>>(py: Python<'py>, name: &str) -> PyResult<T> {
    imported(py, RULES_CONSTANTS_MODULE, name)?.extract()
}

fn uuid_hex(py: Python<'_>) -> PyResult<String> {
    imported(py, "uuid", "uuid4")?
        .call0()?
        .getattr("hex")?
        .extract()
}

/// A new directory below `parent` named `prefix` plus a unique suffix, as `mkdtemp` creates.
fn unique_directory(parent: &Path, prefix: &str) -> PyResult<PathBuf> {
    loop {
        let directory: PathBuf = parent.join(format!(
            "{prefix}{}-{}",
            std::process::id(),
            INPUT_COUNTER.fetch_add(1, Ordering::Relaxed)
        ));
        match std::fs::create_dir(&directory) {
            Ok(()) => return Ok(directory),
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {}
            Err(error) => return Err(error.into()),
        }
    }
}

/// Create `marker` and its folder so hosts can see it.
fn touch(marker: &Path) -> std::io::Result<()> {
    if let Some(parent) = marker.parent() {
        std::fs::create_dir_all(parent)?;
    }
    std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(marker)
        .map(drop)
}

fn remove_file(path: &Path) {
    let _removed: std::io::Result<()> = std::fs::remove_file(path);
}

fn text(path: &Path) -> String {
    path.to_string_lossy().into_owned()
}

fn rules_error(py: Python<'_>, message: String) -> PyErr {
    match imported(py, RULES_ERRORS_MODULE, "RulesError").and_then(|class| class.call1((message,)))
    {
        Ok(instance) => PyErr::from_value(instance),
        Err(error) => error,
    }
}
