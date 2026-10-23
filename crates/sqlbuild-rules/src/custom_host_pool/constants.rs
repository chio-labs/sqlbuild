//! Host fan-out limits, the project subject and cgroup locations.

/// The subject of an invocation that evaluates a project rule.
pub const CUSTOM_RULE_PROJECT_SUBJECT: &str = "";
/// How long one host may take.
pub const HOST_TIMEOUT_MILLIS: u64 = 120_000;
/// Invocations that justify starting one more host.
pub const MIN_INVOCATIONS_PER_HOST: usize = 64;
/// The most hosts one run starts.
pub const MAX_HOSTS: usize = 8;
/// Tracked read keys above which every tracked rule is treated as untracked.
pub const MAX_TRACKED_READS: usize = 100_000;
/// The mounted cgroup hierarchy.
pub const CGROUP_ROOT: &str = "/sys/fs/cgroup";
/// This process's cgroup memberships.
pub const PROC_CGROUP: &str = "/proc/self/cgroup";
/// The cgroup v1 CPU controller name.
pub(crate) const CGROUP_V1_CPU_CONTROLLER: &str = "cpu";
/// Directory names a cgroup v1 CPU controller may be mounted under.
pub(crate) const CGROUP_V1_CPU_DIRECTORIES: [&str; 3] = ["cpu", "cpu,cpuacct", "cpuacct,cpu"];

/// The `RulesError` message of a malformed host payload.
pub(crate) const INVALID_PAYLOAD: &str = "custom rule host returned an invalid payload";
/// The `RulesError` message of a malformed evaluation.
pub(crate) const INVALID_EVALUATION: &str = "custom rule host returned an invalid evaluation";
/// The `RulesError` message of findings that are not a list.
pub(crate) const INVALID_FINDINGS: &str = "custom rule host returned invalid findings";

/// The `compile_timings` key of every custom-rule invocation the hosts ran.
pub const CUSTOM_RULES_INVOCATIONS_KEY: &str = "custom_rules_invocations";
/// The `compile_timings` key of the hosts' module-state monitor CPU.
pub const CUSTOM_RULES_MONITOR_KEY: &str = "custom_rules_monitor_cpu_ms";
/// The `compile_timings` key of the hosts' runtime-guard check CPU.
pub const CUSTOM_RULES_GUARD_KEY: &str = "custom_rules_guard_cpu_ms";
/// The prefix of one rule code's `compile_timings` keys: `custom_rules.<code>.<measure>`.
pub(crate) const CUSTOM_RULE_KEY_PREFIX: &str = "custom_rules.";
pub(crate) const NANOSECONDS_PER_MILLISECOND: u64 = 1_000_000;
