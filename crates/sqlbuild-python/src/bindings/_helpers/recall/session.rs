//! The invocation's Recall session: started before the command runs and closed after it returns.

use std::io::ErrorKind;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::{Duration, Instant, SystemTime};

use pyo3::prelude::{Bound, PyAny, PyAnyMethods, PyResult, Python};
use sqlbuild_cli::dispatch::models::CommandFacts;
use sqlbuild_recall::records::main::format_timestamp::format_timestamp;
use sqlbuild_recall::records::main::sha256_hex::sha256_hex;
use sqlbuild_recall::records::models::{InvocationContext, OutputStream, RowEnvelope};
use sqlbuild_recall::schema::main::ddl_script::ddl_script;
use sqlbuild_recall::schema::models::{DdlOptions, Dialect};
use sqlbuild_recall::settings::main::resolve_recall_settings::resolve_recall_settings;
use sqlbuild_recall::settings::models::{RecallSettings, SettingsRequest, StoreLocation};
use sqlbuild_recall::store::main::observe_store_file::observe_store_file;
use sqlbuild_recall::store::main::quarantine_store::quarantine_store;
use sqlbuild_recall::store::main::store_location_problem::store_location_problem;
use sqlbuild_recall::store::models::QuarantineOutcome;
use sqlbuild_recall::writer::constants::DEFAULT_HEARTBEAT_INTERVAL_MS;
use sqlbuild_recall::writer::main::start_recall_session::start_recall_session;
use sqlbuild_recall::writer::models::{
    DeliverySummary, RecallSession, SessionConfig, SessionStore, SetupOutcome,
};

use crate::bindings::_helpers::native_host::executor::ExecutorHost;
use crate::bindings::_helpers::native_host::host;
use crate::bindings::_helpers::output_capture::records::invocation_context;
use crate::bindings::_helpers::recall::clickhouse_store::{
    ClickHouseLocation, ClickHouseStoreOpener,
};
use crate::bindings::_helpers::recall::console::write_stderr;
use crate::bindings::_helpers::recall::constants::{
    CLOSE_POLL_MS, DDL_NOTICE_PREFIX, HEARTBEAT_ENVIRONMENT, HOST_TOKEN_LENGTH,
    MINIMUM_HEARTBEAT_SECONDS, NOTICE_INTERVAL_SECONDS, QUARANTINE_START_WAIT_MS,
    STDOUT_STREAM_INDEX,
};
use crate::bindings::_helpers::recall::events::escaped_text;
use crate::bindings::_helpers::recall::replacements::{RecallReplacements, in_replacement_sink};
use crate::bindings::_helpers::records::fields::field as native_field;
use crate::bindings::_helpers::rules::config_json::dumped_json;

/// What the invocation records: its session, when enabled, and the resolved target and adapter.
#[derive(Clone, Debug, Default)]
pub(crate) struct InvocationRecall {
    pub(crate) session: Option<Arc<RecallSession>>,
    pub(crate) target: Option<String>,
    pub(crate) adapter: Option<String>,
    /// The command name, for the closing status line.
    pub(crate) command: String,
    /// The resolved settings and project directory, for notices at the end of the run.
    pub(crate) settings: Option<(RecallSettings, PathBuf)>,
    /// The Recall replacement sinks, configured once runtime extensions are discovered.
    pub(crate) replacements: Arc<RecallReplacements>,
}

/// The text of an optional attribute value.
fn text_value(value: &Bound<'_, PyAny>) -> PyResult<Option<String>> {
    if value.is_none() {
        return Ok(None);
    }
    escaped_text(&value.str()?).map(Some)
}

fn list_attribute(args: &Bound<'_, PyAny>, name: &str) -> PyResult<Vec<String>> {
    let value: Bound<'_, PyAny> = args.getattr(name)?;
    let mut items: Vec<String> = Vec::new();
    if value.is_none() {
        return Ok(items);
    }
    for item in value.try_iter()? {
        items.push(escaped_text(&item?.str()?)?);
    }
    Ok(items)
}

fn environment(name: &str) -> Option<String> {
    std::env::var_os(name).map(|value| value.to_string_lossy().into_owned())
}

/// `path`'s text when it exists; Recall metadata is best effort, so unreadable means unknown.
fn file_text(path: &Path) -> Option<String> {
    match std::fs::read_to_string(path) {
        Ok(text) => Some(text),
        Err(error) if error.kind() == ErrorKind::NotFound => None,
        Err(_unreadable) => None,
    }
}

fn project_dir(args: &Bound<'_, PyAny>) -> PyResult<PathBuf> {
    let raw: PathBuf = match text_value(&args.getattr("project_dir")?)? {
        Some(directory) => PathBuf::from(directory),
        None => std::env::current_dir()?,
    };
    Ok(std::fs::canonicalize(&raw).unwrap_or(raw))
}

/// The commit `HEAD` names, read from the repository files without running git.
fn git_revision(project_dir: &Path) -> Option<String> {
    let git: PathBuf = project_dir
        .ancestors()
        .map(|directory| directory.join(".git"))
        .find(|candidate| candidate.is_dir())?;
    let head: String = file_text(&git.join("HEAD"))?;
    let Some(reference) = head.trim().strip_prefix("ref: ") else {
        return Some(head.trim().to_owned());
    };
    if let Some(revision) = file_text(&git.join(reference)) {
        return Some(revision.trim().to_owned());
    }
    file_text(&git.join("packed-refs"))?
        .lines()
        .filter_map(|line| line.split_once(' '))
        .find(|(_, name)| *name == reference)
        .map(|(revision, _)| revision.to_owned())
}

fn host_token() -> Option<String> {
    let name: String = file_text(Path::new("/etc/hostname"))
        .or_else(|| environment("COMPUTERNAME"))
        .or_else(|| environment("HOSTNAME"))?;
    Some(sha256_hex(name.trim().as_bytes())[..HOST_TOKEN_LENGTH].to_owned())
}

/// The orchestrator context as JSON; an invalid environment context records none.
fn external_context(py: Python<'_>) -> PyResult<Option<String>> {
    let context: Bound<'_, PyAny> = match invocation_context(py, None) {
        Ok(context) => context,
        Err(error)
            if error.is_instance(py, &host::entry(py, ExecutorHost::OutputCaptureInputError)?) =>
        {
            return Ok(None);
        }
        Err(error) => return Err(error),
    };
    if !context.is_truthy()? {
        return Ok(None);
    }
    Ok(dumped_json(&context)?.map(|encoded| encoded.to_string()))
}

fn heartbeat_interval() -> Duration {
    let default = Duration::from_millis(DEFAULT_HEARTBEAT_INTERVAL_MS);
    let Some(value) = environment(HEARTBEAT_ENVIRONMENT) else {
        return default;
    };
    match value.parse::<f64>() {
        Ok(seconds) if seconds.is_finite() && seconds >= MINIMUM_HEARTBEAT_SECONDS => {
            Duration::from_secs_f64(seconds)
        }
        Ok(_) | Err(_) => default,
    }
}

fn invocation_facts(
    py: Python<'_>,
    (args, facts): (&Bound<'_, PyAny>, &CommandFacts),
    (settings, project_dir): (&RecallSettings, &Path),
) -> PyResult<InvocationContext> {
    let fingerprint_source = format!(
        "{}\u{0}{}\u{0}{}",
        settings.project_adapter.as_deref().unwrap_or_default(),
        settings.destination_database.as_deref().unwrap_or_default(),
        settings.destination_schema.as_deref().unwrap_or_default()
    );
    Ok(InvocationContext {
        command: facts.command.clone(),
        subcommand: facts.subcommand.clone(),
        selection: list_attribute(args, "select")?,
        exclusion: list_attribute(args, "exclude")?,
        project_name: settings.project_name.clone(),
        project_dir_hash: Some(sha256_hex(project_dir.to_string_lossy().as_bytes())),
        target: settings.target.clone(),
        adapter: settings.project_adapter.clone(),
        destination_database: settings.destination_database.clone(),
        destination_schema: settings.destination_schema.clone(),
        destination_fingerprint: Some(sha256_hex(fingerprint_source.as_bytes())),
        sqlbuild_version: Some(env!("CARGO_PKG_VERSION").to_owned()),
        git_revision: git_revision(project_dir),
        git_dirty: None,
        host_token: host_token(),
        pid: Some(std::process::id()),
        external_context: external_context(py)?,
        recall_filter_active: false,
        argv_digest: None,
    })
}

/// Whether a notice for `store` is due, recording it best effort; a missing marker is due.
fn notice_due(project_dir: &Path, store: &str) -> bool {
    let directory: PathBuf = project_dir.join("target");
    let marker: PathBuf = directory.join(format!(
        "{DDL_NOTICE_PREFIX}{}",
        &sha256_hex(store.as_bytes())[..HOST_TOKEN_LENGTH]
    ));
    let modified: std::io::Result<SystemTime> =
        std::fs::metadata(&marker).and_then(|metadata| metadata.modified());
    if let Ok(modified) = modified
        && SystemTime::now()
            .duration_since(modified)
            .is_ok_and(|age| age < Duration::from_secs(NOTICE_INTERVAL_SECONDS))
    {
        return false;
    }
    drop(
        std::fs::create_dir_all(&directory)
            .and_then(|()| std::fs::write(&marker, format_timestamp(SystemTime::now()))),
    );
    true
}

fn target_phrase(settings: &RecallSettings) -> String {
    settings
        .target
        .as_deref()
        .map_or_else(String::new, |target| format!(" for target `{target}`"))
}

/// The DDL notice for an unwritable store, when one is due for it.
fn permission_notice(
    (settings, project_dir): (&RecallSettings, &Path),
    reason: &str,
) -> Option<String> {
    let (dialect, database, place): (Dialect, Option<String>, String) = match &settings.store {
        StoreLocation::Sqlite { path } => (Dialect::Sqlite, None, format!("at {}", path.display())),
        StoreLocation::ClickHouse { database, .. } => (
            Dialect::ClickHouse,
            Some(database.clone()),
            format!("in ClickHouse database `{database}`"),
        ),
        StoreLocation::Unsupported { .. } => return None,
    };
    if !notice_due(project_dir, &place) {
        return None;
    }
    let script = ddl_script(
        dialect,
        &DdlOptions {
            database,
            retention_days: settings.retention_days,
            cluster: None,
        },
    );
    Some(format!(
        "Recall history is not being written{}: {reason}. An administrator can create the \
         store {place} with:\n\n{script}\n",
        target_phrase(settings),
    ))
}

fn unsupported_notice(
    (settings, project_dir): (&RecallSettings, &Path),
    (connection, adapter): (&str, &str),
) -> Option<String> {
    notice_due(project_dir, connection).then(|| {
        format!(
            "Recall history is not being written{}: connection `{connection}` uses adapter \
             `{adapter}`, which this version cannot store Recall history in.\n",
            target_phrase(settings)
        )
    })
}

/// Write `text` to stderr; a notice that cannot be written never changes the command's outcome.
fn notify(py: Python<'_>, text: Option<String>) {
    if let Some(text) = text {
        drop(write_stderr(py, &text));
    }
}

/// Move a store whose file is not a database aside before the command prints anything.
fn quarantined_notice(path: &Path) -> Option<String> {
    let Ok(Some(observed)) = observe_store_file(path) else {
        return None;
    };
    if !observed.header_foreign {
        return None;
    }
    let give_up: Instant = Instant::now() + Duration::from_millis(QUARANTINE_START_WAIT_MS);
    match quarantine_store(path, &observed, (give_up, SystemTime::now())) {
        Ok(QuarantineOutcome::Moved(moved)) => Some(format!(
            "Recall: {} was not a valid database; it was moved to {} and a fresh store was \
             started.\n",
            path.display(),
            moved.display()
        )),
        Ok(QuarantineOutcome::Kept | QuarantineOutcome::LockBusy) => None,
        Err(error) => Some(format!("Recall history is not being written: {error}.\n")),
    }
}

fn started_session(
    py: Python<'_>,
    (args, identity, facts): (&Bound<'_, PyAny>, &Bound<'_, PyAny>, &CommandFacts),
    (settings, project_dir): (&RecallSettings, &Path),
) -> PyResult<Option<Arc<RecallSession>>> {
    let store: SessionStore = match &settings.store {
        StoreLocation::Sqlite { path } => {
            notify(py, quarantined_notice(path));
            if let Some(reason) = store_location_problem(path) {
                notify(py, permission_notice((settings, project_dir), &reason));
                return Ok(None);
            }
            SessionStore::Sqlite(path.clone())
        }
        StoreLocation::ClickHouse {
            config, database, ..
        } => SessionStore::Hosted(Arc::new(ClickHouseStoreOpener {
            location: ClickHouseLocation::new(config, database, settings.retention_days),
            retention_notice: notice_due,
            project_dir: project_dir.to_path_buf(),
        })),
        StoreLocation::Unsupported {
            connection,
            adapter,
        } => {
            notify(
                py,
                unsupported_notice((settings, project_dir), (connection, adapter)),
            );
            return Ok(None);
        }
    };
    let Some(invocation_id) = text_value(&native_field(identity, "invocation_id")?)? else {
        return Ok(None);
    };
    let context = invocation_facts(py, (args, facts), (settings, project_dir))?;
    let session = start_recall_session(SessionConfig {
        store,
        maintenance_owner: format!(
            "{}:{}",
            context.host_token.as_deref().unwrap_or("host"),
            std::process::id()
        ),
        envelope: RowEnvelope {
            invocation_id,
            invocation_started_at: format_timestamp(SystemTime::now()),
            producer_version: env!("CARGO_PKG_VERSION").to_owned(),
        },
        context,
        retention_days: settings.retention_days,
        shutdown_timeout: Duration::from_millis(settings.shutdown_timeout_ms),
        diagnostics_min_severity: settings.diagnostics_min_severity.clone(),
        max_output_bytes: settings.max_output_bytes,
        heartbeat_interval: heartbeat_interval(),
        setup_budget: Duration::ZERO,
        maintenance: true,
        defer_context: true,
    });
    Ok(Some(Arc::new(session)))
}

/// Begin recording when Recall is enabled, without waiting on the store; invalid settings record nothing and the command reports them.
pub(crate) fn start_invocation_recall(
    py: Python<'_>,
    args: &Bound<'_, PyAny>,
    identity: &Bound<'_, PyAny>,
    facts: &CommandFacts,
) -> PyResult<InvocationRecall> {
    let project_dir: PathBuf = project_dir(args)?;
    let request = SettingsRequest {
        project_dir: project_dir.clone(),
        selected_target: text_value(&args.getattr("target")?)?,
    };
    let Ok(settings) = resolve_recall_settings(&request) else {
        return Ok(InvocationRecall::default());
    };
    let session: Option<Arc<RecallSession>> = if settings.enabled && settings.project_name.is_some()
    {
        started_session(py, (args, identity, facts), (&settings, &project_dir))?
    } else {
        None
    };
    Ok(InvocationRecall {
        session,
        target: settings.target.clone(),
        adapter: settings.project_adapter.clone(),
        command: facts.command.clone().unwrap_or_default(),
        settings: Some((settings, project_dir)),
        replacements: Arc::default(),
    })
}

/// The closing sentence after a Recall notice, so the command's own outcome stays the last word.
fn final_status(command: &str, exit_code: Option<i64>) -> String {
    match exit_code {
        Some(0) => {
            format!("sqb {command} completed successfully; only its Recall history is affected.\n")
        }
        Some(code) => format!("sqb {command} failed with exit code {code}.\n"),
        None => format!("sqb {command} failed.\n"),
    }
}

/// What Recall must tell the user about this run once delivery has finished.
fn closing_notices(recall: &InvocationRecall, session: &RecallSession) -> Vec<String> {
    let mut notices: Vec<String> = session
        .notices()
        .into_iter()
        .map(|notice| {
            if notice.ends_with('\n') {
                format!("Recall: {notice}")
            } else {
                format!("Recall: {notice}.\n")
            }
        })
        .collect();
    if let (Some(SetupOutcome::PermissionDenied { reason }), Some((settings, project_dir))) =
        (session.wait_for_setup(Duration::ZERO), &recall.settings)
    {
        notices.extend(permission_notice((settings, project_dir), &reason));
        return notices;
    }
    let summary: DeliverySummary = session.summary();
    let total = summary.total();
    if total.dropped > 0 || total.failed > 0 {
        let reason = summary
            .degraded_reason
            .as_deref()
            .map_or_else(String::new, |reason| format!(": {reason}"));
        notices.push(format!(
            "warning: Recall history for this run is incomplete ({} dropped, {} failed){reason}\n",
            total.dropped, total.failed
        ));
    }
    notices
}

/// Close the session within its shutdown budget; a further interrupt stops waiting at once. Notices end with the command's own outcome.
pub(crate) fn finish_invocation_recall(
    py: Python<'_>,
    recall: &InvocationRecall,
    exit_code: Option<i64>,
) -> PyResult<()> {
    let Some(session) = &recall.session else {
        return Ok(());
    };
    session.begin_close();
    while !py.detach(|| session.wait_closed(Duration::from_millis(CLOSE_POLL_MS))) {
        if let Err(interrupt) = py.check_signals() {
            session.abandon();
            return Err(interrupt);
        }
    }
    let notices: Vec<String> = closing_notices(recall, session);
    if !notices.is_empty() {
        notify(
            py,
            Some(notices.concat() + &final_status(&recall.command, exit_code)),
        );
    }
    Ok(())
}

/// Forward bytes a process stream accepted to `session` when it records `invocation_id`.
pub(crate) fn forward_output(
    session: Option<&RecallSession>,
    invocation_id: &str,
    (stream, data): (usize, &[u8]),
) {
    let Some(session) = session.filter(|session| session.invocation_id() == invocation_id) else {
        return;
    };
    if in_replacement_sink() {
        return;
    }
    let stream = if stream == STDOUT_STREAM_INDEX {
        OutputStream::Stdout
    } else {
        OutputStream::Stderr
    };
    session.append_output(stream, data);
}

/// Forward one diagnostic's JSON to `session` for `invocation_id`; unparsable ones are skipped.
pub(crate) fn forward_diagnostic(
    session: Option<&RecallSession>,
    invocation_id: &str,
    diagnostic_json: &str,
) {
    if let Some(session) = session.filter(|session| session.invocation_id() == invocation_id) {
        drop(session.publish_diagnostic(diagnostic_json));
    }
}
