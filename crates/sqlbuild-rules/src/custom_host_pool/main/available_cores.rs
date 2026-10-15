//! CPUs available to this process, including container CPU quotas.

use std::path::Path;

use crate::custom_host_pool::_helpers::cgroups::cgroup_quotas;

/// The process CPU count capped by any cgroup quota listed in `proc_cgroup`, at least one.
#[must_use]
pub fn available_cores(process_cpus: usize, (cgroup_root, proc_cgroup): (&Path, &Path)) -> usize {
    let entries: Vec<String> = std::fs::read_to_string(proc_cgroup)
        .map(|text| text.lines().map(str::to_owned).collect())
        .unwrap_or_default();
    cgroup_quotas(cgroup_root, &entries)
        .into_iter()
        .fold(process_cpus.max(1), usize::min)
        .max(1)
}
