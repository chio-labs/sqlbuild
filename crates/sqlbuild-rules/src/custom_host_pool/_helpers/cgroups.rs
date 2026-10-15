//! cgroup v1 and v2 CPU quotas along this process's cgroup paths.

use std::path::{Path, PathBuf};

use crate::custom_host_pool::constants::{CGROUP_V1_CPU_CONTROLLER, CGROUP_V1_CPU_DIRECTORIES};

/// Every CPU quota, in whole CPUs rounded up, along each cgroup membership listed in `entries`.
pub(crate) fn cgroup_quotas(cgroup_root: &Path, entries: &[String]) -> Vec<usize> {
    let fallback: [String; 1] = ["0::/".to_owned()];
    let entries: &[String] = if entries.is_empty() {
        &fallback
    } else {
        entries
    };
    let mut quotas: Vec<usize> = Vec::new();
    for entry in entries {
        let remainder: &str = entry.split_once(':').map_or("", |(_, rest)| rest);
        let (controllers, path): (&str, &str) =
            remainder.split_once(':').unwrap_or((remainder, ""));
        if controllers.is_empty() {
            for directory in directories(cgroup_root, path) {
                quotas.extend(cpu_max_quota(&directory.join("cpu.max")));
            }
        } else if controllers
            .split(',')
            .any(|name| name == CGROUP_V1_CPU_CONTROLLER)
        {
            for name in std::iter::once(controllers).chain(CGROUP_V1_CPU_DIRECTORIES) {
                for directory in directories(&cgroup_root.join(name), path) {
                    quotas.extend(cfs_quota(&directory));
                }
            }
        }
    }
    quotas
}

/// The cgroup directory's ancestors from the hierarchy root down to it.
fn directories(base: &Path, relative: &str) -> Vec<PathBuf> {
    let mut directory: PathBuf = base.to_path_buf();
    let mut found: Vec<PathBuf> = vec![directory.clone()];
    for part in Path::new(relative.trim_matches('/')).components() {
        directory = directory.join(part);
        found.push(directory.clone());
    }
    found
}

/// cgroup v2 `cpu.max`: `max <period>` is unlimited, else `<quota> <period>`.
fn cpu_max_quota(path: &Path) -> Option<usize> {
    let Ok(text) = std::fs::read_to_string(path) else {
        return None;
    };
    let fields: Vec<&str> = text.split_whitespace().collect();
    match fields.as_slice() {
        [quota, period] => quota_cpus(quota, period),
        _ => None,
    }
}

/// cgroup v1 `cpu.cfs_quota_us` and `cpu.cfs_period_us`; a negative quota is unlimited.
fn cfs_quota(directory: &Path) -> Option<usize> {
    let (Ok(quota), Ok(period)) = (
        std::fs::read_to_string(directory.join("cpu.cfs_quota_us")),
        std::fs::read_to_string(directory.join("cpu.cfs_period_us")),
    ) else {
        return None;
    };
    quota_cpus(quota.trim(), period.trim())
}

fn quota_cpus(quota: &str, period: &str) -> Option<usize> {
    let (Ok(quota), Ok(period)) = (quota.parse::<i64>(), period.parse::<i64>()) else {
        return None;
    };
    if quota <= 0 || period <= 0 {
        return None;
    }
    match usize::try_from(quota.div_euclid(period) + i64::from(quota.rem_euclid(period) != 0)) {
        Ok(cpus) => Some(cpus.max(1)),
        Err(_) => None,
    }
}
