//! Python modules, thread names and wait limits of native lifecycle-event export.

pub(crate) const SCOPE_CONTEXT_VARIABLE: &str = "sqlbuild_event_exporter_command_scope";
pub(crate) const DISPATCHER_THREAD_NAME: &str = "sqlbuild-event-exporter-dispatcher";
pub(crate) const NOTIFIER_THREAD_NAME: &str = "sqlbuild-event-exporter-notifier";
pub(crate) const HEALTH_THREAD_NAME: &str = "sqlbuild-event-exporter-health";
pub(crate) const OUTPUT_SINK_THREAD_NAME: &str = "sqlbuild-command-output-sink";
/// Prefix of each exporter's long-lived delivery thread name.
pub(crate) const INVOCATION_THREAD_PREFIX: &str = "sqlbuild-event-exporter-";
/// Attribute naming the worker of a long-lived dispatcher thread, for the exit hook.
pub(crate) const WORKER_ATTRIBUTE: &str = "_sqlbuild_event_exporter_worker";
/// The longest single wait of a polling delivery loop, as the Python dispatcher polled.
pub(crate) const POLL_SECONDS: f64 = 0.01;
/// Extra time `shutdown` waits for the dispatcher thread beyond the drain deadline.
pub(crate) const JOIN_GRACE_SECONDS: f64 = 0.05;
/// How long shutdown and interpreter exit wait for each stopped dispatcher thread.
pub(crate) const EXIT_JOIN_SECONDS: f64 = 1.0;
/// The most attempts one exporter's delivery thread holds, at most the queue capacity; more stay queued.
pub(crate) const LANE_WINDOW: usize = 64;
/// The longest a finalizer waits for sink calls still running after shutdown before it runs anyway.
pub(crate) const IDLE_WAIT_SECONDS: f64 = 1.0;
/// No time left before a deadline.
pub(crate) const NO_SECONDS: f64 = 0.0;
