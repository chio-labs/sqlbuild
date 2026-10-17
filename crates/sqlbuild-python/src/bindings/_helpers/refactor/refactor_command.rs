//! `sqb rename` and `sqb mv`: plan from compiler facts, verify in a scratch copy, then write.

use std::cell::RefCell;
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::time::Instant;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::{
    Bound, PyAny, PyAnyMethods, PyErr, PyModule, PyModuleMethods, PyResult, Python,
};
use pyo3::types::{PyDict, PyDictMethods};
use pyo3::{pyfunction, wrap_pyfunction};
use sqlbuild_analysis::lineage_command::models::LineageKey;
use sqlbuild_core::cli_text::main::format_count_noun::format_count_noun;
use sqlbuild_core::cli_text::models::CliStyle;
use sqlbuild_refactor::refactor_command::main::layer_move_suggestion::layer_move_suggestion;
use sqlbuild_refactor::refactor_command::main::refactor_request_for_target::refactor_request_for_target;
use sqlbuild_refactor::refactor_command::main::render_refactor_json::render_refactor_json;
use sqlbuild_refactor::refactor_command::main::render_refactor_text::render_refactor_text;
use sqlbuild_refactor::refactor_command::models::{
    LayerMove, RefactorDiagnostic, RefactorStatus, RefactorTargetRequest,
};
use sqlbuild_refactor::refactoring::errors::{RefactorError, RefactorErrorKind};
use sqlbuild_refactor::refactoring::main::commit_refactor_plan::commit_refactor_plan;
use sqlbuild_refactor::refactoring::main::plan_refactor::plan_refactor;
use sqlbuild_refactor::refactoring::main::stage_refactor_plan::stage_refactor_plan;
use sqlbuild_refactor::refactoring::main::with_model_migration::with_model_migration;
use sqlbuild_refactor::refactoring::models::{
    DeclarationPlacement, ModelFacts, RefactorFacts, RefactorOperation, RefactorPlan,
    RefactorRequest,
};
use sqlbuild_refactor::refactoring::types::Originals;

use crate::bindings::_helpers::boundary::panics::{NativeCompilerError, compiler_guard};
use crate::bindings::_helpers::build_progress::transient_status::status_reporter;
use crate::bindings::_helpers::lineage::lineage_index::lineage_key;
use crate::bindings::_helpers::presentation_text::terminal::stdout_supports_color;
use crate::bindings::_helpers::records::construct::error_class;
use crate::bindings::_helpers::records::fields::field as native_field;
use crate::bindings::_helpers::records::fields::mapping_items;
use crate::bindings::_helpers::records::ids::ErrorId;
use crate::bindings::_helpers::refactor::offline_compile::{OfflineCompile, compile_for_refactor};
use crate::bindings::_helpers::refactor::refactor_facts::{
    declaration_placement, model_facts, refactor_facts,
};

const STAGING_PREFIX: &str = "sqb-refactor-";
const MOVE_COMMAND: &str = "mv";
const EDIT_ERROR_CODE: &str = "C957";
const WRITE_ERROR_CODE: &str = "C958";

fn imported<'py>(py: Python<'py>, module: &str, name: &str) -> PyResult<Bound<'py, PyAny>> {
    py.import(module)?.getattr(name)
}

/// `CliUserError(message, code=..., help=...)`.
fn user_error(py: Python<'_>, (message, code, help): (String, &str, Option<String>)) -> PyErr {
    let raised = (|| {
        let options: Bound<'_, PyDict> = PyDict::new(py);
        options.set_item("code", code)?;
        options.set_item("help", help)?;
        error_class(py, ErrorId::CliUser)?.call((message,), Some(&options))
    })();
    match raised {
        Ok(error) => PyErr::from_value(error),
        Err(error) => error,
    }
}

/// The Python exception a native refactoring failure becomes.
fn refactor_error(py: Python<'_>, error: RefactorError) -> PyErr {
    let class = |name: ErrorId| -> PyErr {
        match error_class(py, name).and_then(|class| class.call1((error.message.clone(),))) {
            Ok(raised) => PyErr::from_value(raised),
            Err(failure) => failure,
        }
    };
    match error.kind {
        RefactorErrorKind::Input => user_error(py, (error.message, &error.code, error.help)),
        RefactorErrorKind::Edit => user_error(py, (error.message, EDIT_ERROR_CODE, None)),
        RefactorErrorKind::Write => user_error(py, (error.message, WRITE_ERROR_CODE, error.help)),
        RefactorErrorKind::Value => class(ErrorId::RefactorValue),
        RefactorErrorKind::Io => class(ErrorId::RefactorIO),
        RefactorErrorKind::Internal => NativeCompilerError::new_err(error.message),
    }
}

/// One offline compile: its project facts and errors.
struct Compiled<'py> {
    project: Bound<'py, PyAny>,
    errors: Vec<Bound<'py, PyAny>>,
}

fn compile<'py>(py: Python<'py>, project_dir: &Path, no_cache: bool) -> PyResult<Compiled<'py>> {
    let compiled: OfflineCompile<'py> = compile_for_refactor(py, project_dir, no_cache)?;
    Ok(Compiled {
        project: compiled.project,
        errors: compiled.errors,
    })
}

fn optional_posix(path: &Bound<'_, PyAny>) -> PyResult<Option<String>> {
    if path.is_none() {
        return Ok(None);
    }
    Ok(Some(path.call_method0("as_posix")?.extract()?))
}

/// The edited project's errors, paths inside the scratch copy made relative to it.
fn relative_diagnostics(
    errors: &[Bound<'_, PyAny>],
    staging_dir: &Path,
) -> PyResult<Vec<RefactorDiagnostic>> {
    let mut diagnostics: Vec<RefactorDiagnostic> = Vec::new();
    for error in errors {
        let path: Option<String> = optional_posix(&native_field(error, "path")?)?.map(|path| {
            let candidate: &Path = Path::new(&path);
            match candidate.strip_prefix(staging_dir) {
                Ok(relative) if candidate.is_absolute() => relative.to_string_lossy().into_owned(),
                _ => path,
            }
        });
        diagnostics.push(RefactorDiagnostic {
            code: native_field(error, "code")?.extract()?,
            message: native_field(error, "message")?.extract()?,
            path,
            line: native_field(error, "line")?.extract()?,
        });
    }
    Ok(diagnostics)
}

/// Print each compile error to stderr as `error[code] path: message`.
fn write_errors(py: Python<'_>, errors: &[Bound<'_, PyAny>]) -> PyResult<()> {
    let stderr: Bound<'_, PyAny> = py.import("sys")?.getattr("stderr")?;
    for error in errors {
        let location: String = optional_posix(&native_field(error, "path")?)?
            .map_or_else(String::new, |path| format!("{path}: "));
        let code: String = native_field(error, "code")?.str()?.extract()?;
        let message: String = native_field(error, "message")?.str()?.extract()?;
        stderr.call_method1("write", (format!("error[{code}] {location}{message}\n"),))?;
    }
    Ok(())
}

fn files(plan: &RefactorPlan) -> String {
    format_count_noun(
        i64::try_from(plan.changes.len()).unwrap_or(i64::MAX),
        "file",
        None,
    )
}

/// The Python transient status reporter on the command's progress stream.
struct Status<'py> {
    reporter: Bound<'py, PyAny>,
}

impl Status<'_> {
    fn start(&self, message: &str) -> PyResult<()> {
        self.reporter.call_method1("start", (message,))?;
        Ok(())
    }

    fn complete(&self, message: &str) -> PyResult<()> {
        let options: Bound<'_, PyDict> = PyDict::new(self.reporter.py());
        options.set_item("message", message)?;
        self.reporter.call_method("complete", (), Some(&options))?;
        Ok(())
    }

    fn error(&self, message: &str) -> PyResult<()> {
        self.reporter.call_method1("error", (message,))?;
        Ok(())
    }

    fn close(&self) -> PyResult<()> {
        self.reporter.call_method0("close")?;
        Ok(())
    }
}

/// The command's options and output settings.
struct Command<'py> {
    request: Bound<'py, PyAny>,
    project_dir: PathBuf,
    use_color: bool,
    json_output: bool,
}

/// Where a refactoring stopped: its plan, terminal status and compile errors.
struct Outcome {
    plan: RefactorPlan,
    status: RefactorStatus,
    diagnostics: Vec<RefactorDiagnostic>,
}

/// A plan verified in the scratch copy, with its originals and the edited project's errors.
struct Verified {
    plan: RefactorPlan,
    originals: Originals,
    diagnostics: Vec<RefactorDiagnostic>,
}

fn target_lookup(all_keys: &Bound<'_, PyAny>) -> PyResult<HashMap<String, LineageKey>> {
    let mut names: HashMap<String, LineageKey> = HashMap::new();
    for item in mapping_items(all_keys)?.try_iter()? {
        let (name, key): (String, Bound<'_, PyAny>) = item?.extract()?;
        names.insert(name, lineage_key(&key)?);
    }
    Ok(names)
}

fn target_request(request: &Bound<'_, PyAny>) -> PyResult<RefactorTargetRequest> {
    Ok(RefactorTargetRequest {
        is_move: native_field(request, "command")?
            .str()?
            .extract::<String>()?
            == MOVE_COMMAND,
        target: native_field(request, "target")?.extract()?,
        new_name: native_field(request, "new_name")?.extract()?,
        destination: native_field(request, "destination")?.extract()?,
        cascade: native_field(request, "cascade")?.extract()?,
    })
}

fn plan(
    py: Python<'_>,
    project: &Bound<'_, PyAny>,
    request: &RefactorRequest,
) -> PyResult<RefactorPlan> {
    let facts: RefactorFacts = refactor_facts(project, request)?;
    let host_error: RefCell<Option<PyErr>> = RefCell::new(None);
    let host = |model: &str, destination: &str| -> Result<DeclarationPlacement, RefactorError> {
        declaration_placement(project, (model, destination)).map_err(|error| {
            host_error.replace(Some(error));
            RefactorError::internal("the declaration-move host failed")
        })
    };
    let planned: Result<RefactorPlan, RefactorError> = plan_refactor(&facts, request, &host);
    if let Some(error) = host_error.into_inner() {
        return Err(error);
    }
    planned.map_err(|error| refactor_error(py, error))
}

fn stage(
    py: Python<'_>,
    (project_dir, staging_dir): (&Path, &Path),
    plan: &RefactorPlan,
    copy_inputs: bool,
) -> PyResult<Originals> {
    stage_refactor_plan(project_dir, staging_dir, plan, copy_inputs)
        .map_err(|error| refactor_error(py, error))
}

/// Verify the plan in a scratch copy, adding model migrations when the relation moves.
fn verify(
    py: Python<'_>,
    command: &Command<'_>,
    (before, mut plan): (&Bound<'_, PyAny>, RefactorPlan),
    (staging_dir, status): (&Path, &Status<'_>),
) -> PyResult<Result<Verified, Outcome>> {
    let project_dir: &Path = &command.project_dir;
    status.start("Verifying the edited project compiles...")?;
    let mut originals: Originals = stage(py, (project_dir, staging_dir), &plan, true)?;
    let mut after: Compiled<'_> = compile(py, staging_dir, true)?;
    if plan.request.operation != RefactorOperation::RenameColumn {
        let before_facts: Vec<ModelFacts> = model_facts(before)?.unwrap_or_default();
        let after_facts: Option<Vec<ModelFacts>> = model_facts(&after.project)?;
        let migrated: RefactorPlan =
            with_model_migration(&plan, &before_facts, after_facts.as_deref(), &originals);
        if !migrated.blocking.is_empty() {
            status.error("Refused: the renamed model's history cannot be kept.")?;
            return Ok(Err(Outcome {
                plan: migrated,
                status: RefactorStatus::Refused,
                diagnostics: Vec::new(),
            }));
        }
        if migrated.migrations != plan.migrations {
            plan = migrated;
            originals = stage(py, (project_dir, staging_dir), &plan, false)?;
            after = compile(py, staging_dir, true)?;
        }
    }
    let diagnostics: Vec<RefactorDiagnostic> = relative_diagnostics(&after.errors, staging_dir)?;
    Ok(Ok(Verified {
        plan,
        originals,
        diagnostics,
    }))
}

fn run(py: Python<'_>, command: &Command<'_>, status: &Status<'_>) -> PyResult<Option<Outcome>> {
    let started: Instant = Instant::now();
    status.start("Compiling project...")?;
    let before: Compiled<'_> = compile(py, &command.project_dir, false)?;
    if before.project.is_none() || !before.errors.is_empty() {
        status.error("Project does not compile; fix it before renaming (sqb compile)")?;
        write_errors(py, &before.errors)?;
        return Ok(None);
    }
    status.complete(&format!(
        "Compiled project. ({:.2}s)",
        started.elapsed().as_secs_f64()
    ))?;
    let names: HashMap<String, LineageKey> = target_lookup(&native_field(
        &native_field(&before.project, "graph")?,
        "all_keys",
    )?)?;
    let lookup = |name: &str| names.get(name).cloned();
    let request: RefactorRequest =
        refactor_request_for_target(&target_request(&command.request)?, &lookup)
            .map_err(|error| refactor_error(py, error))?;
    status.start("Planning edits...")?;
    let planned: RefactorPlan = plan(py, &before.project, &request)?;
    status.complete(&format!("Planned edits to {}.", files(&planned)))?;
    if !planned.blocking.is_empty() || !planned.manual.is_empty() {
        status.error("Refused: some references cannot be rewritten safely.")?;
        return Ok(Some(Outcome {
            plan: planned,
            status: RefactorStatus::Refused,
            diagnostics: Vec::new(),
        }));
    }
    let options: Bound<'_, PyDict> = PyDict::new(py);
    options.set_item("prefix", STAGING_PREFIX)?;
    let staging: Bound<'_, PyAny> =
        imported(py, "tempfile", "TemporaryDirectory")?.call((), Some(&options))?;
    let staging_dir: PathBuf = native_field(&staging, "name")?.extract()?;
    let verified = verify(
        py,
        command,
        (&before.project, planned),
        (&staging_dir, status),
    );
    staging.call_method0("cleanup")?;
    let Verified {
        plan,
        originals,
        diagnostics,
    } = match verified? {
        Ok(verified) => verified,
        Err(outcome) => return Ok(Some(outcome)),
    };
    if !diagnostics.is_empty() {
        status.error("Verification failed: the edited project does not compile.")?;
        return Ok(Some(Outcome {
            plan,
            status: RefactorStatus::CompileFailed,
            diagnostics,
        }));
    }
    status.complete("Verified: the edited project compiles.")?;
    if native_field(&command.request, "dry_run")?.extract::<bool>()? {
        return Ok(Some(Outcome {
            plan,
            status: RefactorStatus::DryRun,
            diagnostics: Vec::new(),
        }));
    }
    status.start(&format!("Writing {}...", files(&plan)))?;
    commit_refactor_plan(&command.project_dir, &originals, &plan)
        .map_err(|error| refactor_error(py, error))?;
    status.complete(&format!("Wrote {}.", files(&plan)))?;
    Ok(Some(Outcome {
        plan,
        status: RefactorStatus::Applied,
        diagnostics: Vec::new(),
    }))
}

fn finish(py: Python<'_>, command: &Command<'_>, outcome: &Outcome) -> PyResult<i32> {
    let output: String = if command.json_output {
        render_refactor_json(&outcome.plan, outcome.status, &outcome.diagnostics)
            .map_err(|error| PyValueError::new_err(format!("{error:?}")))?
    } else {
        let project_dir: Bound<'_, PyAny> = native_field(&command.request, "project_dir")?;
        let project_dir: Option<String> = if project_dir.is_none() {
            None
        } else {
            Some(project_dir.str()?.extract()?)
        };
        let layer_move: Option<LayerMove> = layer_move_suggestion(
            &outcome.plan,
            &outcome.diagnostics,
            (project_dir.as_deref(), cfg!(windows)),
        );
        render_refactor_text(
            &outcome.plan,
            (outcome.status, &outcome.diagnostics),
            layer_move.as_ref(),
            CliStyle {
                use_color: command.use_color,
            },
        )
    };
    py.import("sys")?
        .getattr("stdout")?
        .call_method1("write", (output,))?;
    Ok(i32::from(!matches!(
        outcome.status,
        RefactorStatus::Applied | RefactorStatus::DryRun
    )))
}

/// Plan, verify in a scratch copy, and write one rename or move.
#[pyfunction]
#[pyo3(signature = (*, request))]
pub(crate) fn run_refactor_command(py: Python<'_>, request: &Bound<'_, PyAny>) -> PyResult<i32> {
    let project_dir: Bound<'_, PyAny> = match native_field(request, "project_dir")? {
        directory if !directory.is_none() => directory,
        _ => py.import("pathlib")?.getattr("Path")?.call_method0("cwd")?,
    };
    let json_output: bool = native_field(request, "json_output")?.extract()?;
    let use_color: bool =
        !native_field(request, "no_color")?.extract::<bool>()? && stdout_supports_color(py)?;
    let command: Command<'_> = Command {
        request: request.clone(),
        project_dir: project_dir.call_method0("resolve")?.extract()?,
        use_color,
        json_output,
    };
    let stream: Bound<'_, PyAny> =
        py.import("sys")?
            .getattr(if json_output { "stderr" } else { "stdout" })?;
    let status: Status<'_> = Status {
        reporter: status_reporter(&stream, use_color)?,
    };
    let result: PyResult<Option<Outcome>> = compiler_guard(|| run(py, &command, &status));
    status.close()?;
    match result? {
        None => Ok(1),
        Some(outcome) => finish(py, &command, &outcome),
    }
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(run_refactor_command, module)?)?;
    Ok(())
}
